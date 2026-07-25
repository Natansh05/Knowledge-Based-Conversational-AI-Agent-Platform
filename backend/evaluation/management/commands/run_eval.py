# evaluation.management.commands.run_eval
"""
Run the golden set through the live pipeline and score it.

    python manage.py run_eval --tenant acme --agent 3

Writes report.json, report.md and eval_records.json (the Ragas input) to --out.
"""
import json
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from evaluation.dataset.schema import read_jsonl, resolve_labels
from evaluation.metrics.application import aggregate_traces
from evaluation.metrics.ranking import aggregate, evaluate_ranking
from evaluation.metrics.refusal import evaluate_refusal, status_confusion
from evaluation.report import render_markdown
from evaluation.trace import QueryTrace

DEFAULT_GOLDEN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "dataset", "golden_set.jsonl",
)
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports",
)


class Command(BaseCommand):
    help = "Evaluate the RAG pipeline against a golden set."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--agent", required=True, type=int)
        parser.add_argument("--golden", default=DEFAULT_GOLDEN)
        parser.add_argument("--out", default=DEFAULT_OUT)
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Evaluate only the first N records (smoke runs).",
        )
        parser.add_argument("--sleep", type=float, default=0.0)
        parser.add_argument(
            "--keep-cache", action="store_true",
            help="Do NOT disable the semantic cache. Off by default: with the "
                 "cache on you measure the cache, not the pipeline.",
        )

    def handle(self, *args, **options):
        from agent.services.agent_service import generate_agent_answer

        if not os.path.exists(options["golden"]):
            raise CommandError(
                f"golden set not found: {options['golden']}\n"
                "Build one first with: python manage.py build_golden_set "
                f"--tenant {options['tenant']} --agent {options['agent']}"
            )

        records, golden_meta = read_jsonl(options["golden"])
        if options["limit"]:
            records = records[:options["limit"]]
        if not records:
            raise CommandError("golden set is empty")

        cache_disabled = not options["keep_cache"]
        if cache_disabled:
            # _enabled() reads this via getattr at call time, so assigning here
            # is enough for the duration of the process.
            settings.SEMANTIC_CACHE_ENABLED = False

        os.makedirs(options["out"], exist_ok=True)

        with schema_context(options["tenant"]):
            from documents.models import DocumentChunk

            resolved, label_report = resolve_labels(records)
            self._warn_on_labels(label_report, golden_meta)

            results = []
            traces = []
            eval_records = []

            for index, record in enumerate(records, start=1):
                trace = QueryTrace()
                try:
                    answer = generate_agent_answer(
                        options["agent"], record.question, record.history,
                        trace=trace, full_ranking=True,
                    )
                except Exception as exc:
                    self.stderr.write(f"  [{record.id}] FAILED: {exc}")
                    continue

                relevant = resolved.get(record.id, {})
                reranked = answer.get("ranked_chunk_ids") or []
                ann = answer.get("ann_chunk_ids") or []

                results.append({
                    "id": record.id,
                    "query_type": record.query_type,
                    "expected_status": record.expected_status,
                    "status": answer.get("status", "unknown"),
                    "chunk_ids": answer.get("chunk_ids") or [],
                    "top_score": answer.get("top_score"),
                    "relevant_count": len(relevant),
                    "ranking_rerank": evaluate_ranking(reranked, relevant),
                    "ranking_ann": evaluate_ranking(ann, relevant),
                })
                traces.append(trace.to_dict())

                # Ragas input. Contexts are the chunks actually given to the LLM,
                # not the full candidate list — faithfulness must be judged
                # against what the model could actually see.
                context_texts = self._chunk_texts(
                    DocumentChunk, answer.get("chunk_ids") or []
                )
                eval_records.append({
                    "id": record.id,
                    "query_type": record.query_type,
                    "status": answer.get("status", "unknown"),
                    "question": record.question,
                    "answer": answer.get("answer", ""),
                    "contexts": context_texts,
                    "ground_truth": record.ground_truth_answer,
                })

                self.stdout.write(
                    f"  [{index}/{len(records)}] {record.id} "
                    f"status={answer.get('status')} "
                    f"chunks={len(answer.get('chunk_ids') or [])}"
                )
                if options["sleep"]:
                    time.sleep(options["sleep"])

        if not results:
            raise CommandError("every query failed — nothing to report")

        report = self._build_report(
            results, traces, label_report, options, golden_meta, len(records)
        )

        out = options["out"]
        self._write(os.path.join(out, "report.json"), json.dumps(report, indent=2))
        self._write(os.path.join(out, "report.md"), render_markdown(report))
        self._write(
            os.path.join(out, "eval_records.json"),
            json.dumps(eval_records, indent=2),
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nWrote report.json, report.md and eval_records.json to {out}"
        ))
        self.stdout.write("\n" + render_markdown(report))

    # ------------------------------------------------------------------

    def _chunk_texts(self, model, chunk_ids):
        if not chunk_ids:
            return []
        by_id = {
            chunk.id: chunk.text
            for chunk in model.objects.filter(id__in=chunk_ids).only("id", "text")
        }
        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    def _warn_on_labels(self, label_report, golden_meta):
        if label_report.get("stale") or label_report.get("missing"):
            self.stderr.write(self.style.WARNING(
                f"Label resolution: {label_report['matched']} matched, "
                f"{label_report['stale']} stale, {label_report['missing']} missing.\n"
                "Stale labels mean a document changed since the golden set was "
                "built; those labels are excluded. Rebuild the set to restore "
                "full coverage."
            ))
            built_against = golden_meta.get("doc_versions")
            if built_against:
                self.stderr.write(f"  built against doc versions: {built_against}")

    def _build_report(self, results, traces, label_report, options, golden_meta,
                      total_records):
        ranking = {
            "ann": aggregate([r["ranking_ann"] for r in results]),
            "rerank": aggregate([r["ranking_rerank"] for r in results]),
        }

        by_query_type = {}
        for result in results:
            by_query_type.setdefault(result["query_type"], []).append(
                result["ranking_rerank"]
            )
        by_query_type = {
            query_type: aggregate(scores)
            for query_type, scores in by_query_type.items()
        }

        # Ranking metrics segmented by the routing decision, because the three
        # paths are not comparable: partial/ambiguous deliberately return a
        # clarifying question rather than an answer.
        by_status = {}
        for result in results:
            by_status.setdefault(result["status"], []).append(result["ranking_rerank"])
        by_status = {
            status: aggregate(scores) for status, scores in by_status.items()
        }

        return {
            "meta": {
                "tenant": options["tenant"],
                "agent_id": options["agent"],
                "golden_set": options["golden"],
                "records": len(results),
                "records_in_set": total_records,
                "cache_disabled": not options["keep_cache"],
                "golden_meta": golden_meta,
            },
            "label_resolution": label_report,
            "ranking": ranking,
            "by_query_type": by_query_type,
            "by_status": by_status,
            "refusal": evaluate_refusal(results),
            "status_confusion": status_confusion(results),
            "application": aggregate_traces(traces),
            "per_query": results,
            "ragas": None,
        }

    def _write(self, path, content):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
