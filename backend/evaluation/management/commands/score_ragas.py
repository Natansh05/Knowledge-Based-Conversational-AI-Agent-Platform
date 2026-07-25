# evaluation.management.commands.score_ragas
"""
Score `eval_records.json` (produced by run_eval) with Ragas, and merge the
results into report.json / report.md.

    python manage.py score_ragas

Requires the eval dependency group: `uv sync --group eval`.

Only records that produced a *grounded* answer (status "high") are scored. The
other paths are not answers: "partial"/"ambiguous" deliberately return a
clarifying question and "low" returns an out-of-scope message, so faithfulness
and answer-correctness against a reference would score them near zero for doing
exactly what they were designed to do.

API note: this uses ragas' LangchainLLMWrapper, which emits a DeprecationWarning
pointing at llm_factory. llm_factory currently requires either an OpenAI-style
client or the litellm adapter for Gemini, neither of which is installed here, so
the Langchain wrapper is the working path on ragas 0.4.x.
"""
import json
import os
import warnings

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from evaluation.report import render_markdown

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports",
)

# Ragas costs roughly 1-3 LLM calls per metric per sample. Four metrics over a
# full golden set runs into four figures of Gemini calls against an API with no
# rate limiting in this codebase, so the default is a subset.
DEFAULT_LIMIT = 40


class Command(BaseCommand):
    help = "Score eval_records.json with Ragas and merge into the report."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=DEFAULT_OUT)
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
        parser.add_argument(
            "--metrics", default="faithfulness,answer_correctness,"
                                 "context_precision,context_recall",
            help="Comma-separated. Context metrics are the least informative "
                 "here (see the report) — drop them first if rate-limited.",
        )
        parser.add_argument("--model", default="gemini-2.5-flash")

    def handle(self, *args, **options):
        try:
            from datasets import Dataset
            from langchain_core.embeddings import Embeddings
            from langchain_google_genai import ChatGoogleGenerativeAI
            from ragas import evaluate
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
            from ragas import metrics as ragas_metrics
        except ImportError as exc:
            raise CommandError(
                f"eval dependencies missing ({exc}). Install with: "
                "uv sync --group eval"
            )

        records_path = os.path.join(options["out"], "eval_records.json")
        if not os.path.exists(records_path):
            raise CommandError(
                f"{records_path} not found. Run `manage.py run_eval` first."
            )

        with open(records_path, encoding="utf-8") as handle:
            records = json.load(handle)

        scorable = [
            r for r in records
            if r.get("status") == "high" and r.get("contexts") and r.get("answer")
        ]
        if not scorable:
            raise CommandError(
                "no records with status 'high' and retrieved contexts — nothing "
                "Ragas can meaningfully score."
            )

        skipped = len(records) - len(scorable)
        scorable = scorable[:options["limit"]]
        self.stdout.write(
            f"Scoring {len(scorable)} grounded records "
            f"({skipped} non-grounded skipped) with {options['model']}"
        )

        os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
        llm = LangchainLLMWrapper(
            ChatGoogleGenerativeAI(model=options["model"], temperature=0)
        )

        class _LocalEmbeddings(Embeddings):
            """
            Reuse the pipeline's own all-mpnet-base-v2 model, which is already
            loaded, rather than paying for a remote embedding API. Only
            answer_correctness needs embeddings.
            """

            def embed_documents(self, texts):
                from rag.processors.embeddings import generate_embeddings
                return generate_embeddings(list(texts))

            def embed_query(self, text):
                from rag.processors.embeddings import generate_embeddings
                return generate_embeddings([text])[0]

        embeddings = LangchainEmbeddingsWrapper(_LocalEmbeddings())

        selected = []
        for name in [m.strip() for m in options["metrics"].split(",") if m.strip()]:
            metric = getattr(ragas_metrics, name, None)
            if metric is None:
                raise CommandError(f"unknown ragas metric: {name}")
            selected.append(metric)

        dataset = Dataset.from_list([
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
                "ground_truth": r["ground_truth"],
            }
            for r in scorable
        ])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = evaluate(
                dataset,
                metrics=selected,
                llm=llm,
                embeddings=embeddings,
                show_progress=True,
                # A single malformed judge response should not discard the run.
                raise_exceptions=False,
            )

        scores = self._summarise(result, len(scorable))
        self.stdout.write(self.style.SUCCESS(f"\nRagas: {scores}"))

        self._write(
            os.path.join(options["out"], "ragas_scores.json"),
            json.dumps(scores, indent=2),
        )
        self._merge_into_report(options["out"], scores)

    # ------------------------------------------------------------------

    def _summarise(self, result, n):
        """
        Mean each metric, skipping the NaNs Ragas emits when a judge call fails,
        and record how many samples actually contributed.
        """
        scores = {}
        try:
            frame = result.to_pandas()
        except Exception:
            return {name: {"mean": value, "n": n} for name, value in dict(result).items()}

        for column in frame.columns:
            if column in ("question", "answer", "contexts", "ground_truth",
                          "user_input", "response", "retrieved_contexts",
                          "reference"):
                continue
            series = frame[column].dropna()
            if len(series) == 0:
                scores[column] = {"mean": None, "n": 0}
                continue
            try:
                scores[column] = {"mean": float(series.mean()), "n": int(len(series))}
            except (TypeError, ValueError):
                continue
        return scores

    def _merge_into_report(self, out_dir, scores):
        report_path = os.path.join(out_dir, "report.json")
        if not os.path.exists(report_path):
            self.stderr.write(
                "report.json not found — wrote ragas_scores.json only."
            )
            return

        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)

        report["ragas"] = scores
        self._write(report_path, json.dumps(report, indent=2))
        self._write(
            os.path.join(out_dir, "report.md"), render_markdown(report)
        )
        self.stdout.write(f"Merged Ragas scores into {report_path} and report.md")

    def _write(self, path, content):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
