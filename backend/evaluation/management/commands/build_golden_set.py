# evaluation.management.commands.build_golden_set
"""
Generate a golden evaluation set from a tenant's own ingested documents.

    python manage.py build_golden_set --tenant acme --agent 3

Everything runs inside the tenant schema: documents, agent and chat are
TENANT_APPS, so their tables do not exist in the public schema.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from evaluation.dataset.builder import DEFAULT_LABEL_THRESHOLD, build
from evaluation.dataset.schema import write_jsonl

# The default mix. The out_of_scope stratum is what keeps a threshold sweep
# honest: without it, lowering TOP_SIMILARITY_THRESHOLD appears to improve recall
# while silently destroying the system's ability to refuse.
DEFAULT_COUNTS = {
    "single_hop": 30,
    "multi_part": 15,
    "negation": 10,
    "out_of_scope": 15,
}

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "dataset", "golden_set.jsonl",
)


class Command(BaseCommand):
    help = "Build a golden evaluation set from a tenant agent's documents."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant schema name")
        parser.add_argument("--agent", required=True, type=int, help="Agent id")
        parser.add_argument("--out", default=DEFAULT_OUT)
        parser.add_argument("--seed", type=int, default=1234)
        parser.add_argument(
            "--label-threshold", type=float, default=DEFAULT_LABEL_THRESHOLD,
            help="Cross-encoder score at/above which a non-seed chunk is labelled "
                 "supporting evidence.",
        )
        parser.add_argument(
            "--sleep", type=float, default=0.0,
            help="Seconds to pause between generations; use to stay under the "
                 "Gemini free-tier rate limit.",
        )
        for query_type, default in DEFAULT_COUNTS.items():
            parser.add_argument(
                f"--{query_type.replace('_', '-')}", type=int, default=default,
                dest=query_type,
            )

    def handle(self, *args, **options):
        counts = {qt: options[qt] for qt in DEFAULT_COUNTS if options[qt] > 0}
        if not counts:
            raise CommandError("all strata set to zero — nothing to build")

        with schema_context(options["tenant"]):
            from agent.models import Agent

            try:
                agent = Agent.objects.get(id=options["agent"])
            except Agent.DoesNotExist:
                raise CommandError(
                    f"agent {options['agent']} not found in schema "
                    f"'{options['tenant']}'"
                )

            documents = list(agent.documents.all())
            if not documents:
                raise CommandError(f"agent '{agent}' has no documents attached")

            self.stdout.write(
                f"Building {sum(counts.values())} records for agent {agent.id} "
                f"from {len(documents)} document(s) in schema "
                f"'{options['tenant']}'"
            )

            records, stats = build(
                agent,
                counts,
                label_threshold=options["label_threshold"],
                seed=options["seed"],
                sleep_seconds=options["sleep"],
                log=self.stdout.write,
            )

            # Record which corpus this set was built against, so a later eval run
            # can tell whether the documents have moved underneath the labels.
            meta = {
                "tenant": options["tenant"],
                "agent_id": agent.id,
                "label_threshold": options["label_threshold"],
                "seed": options["seed"],
                "doc_versions": {str(d.id): d.version for d in documents},
                "counts": counts,
                "stats": stats,
            }

            write_jsonl(options["out"], records, meta=meta)

        labelled = sum(len(r.relevant) for r in records)
        in_scope = [r for r in records if r.query_type != "out_of_scope"]

        summary = [
            f"\nWrote {len(records)} records to {options['out']}",
            f"  generated={stats['generated']} blocked={stats['blocked']} "
            f"failed={stats['failed']}",
            f"  {labelled} chunk labels across {len(in_scope)} in-scope queries",
        ]
        if in_scope:
            # An average near 1.00 means label completion found nothing beyond the
            # seed chunks, which usually points at too high a --label-threshold.
            # Recall@k would then be measuring an artificially sparse ground truth.
            summary.append(
                f"  {labelled / len(in_scope):.2f} labels per in-scope query"
            )
        self.stdout.write(self.style.SUCCESS("\n".join(summary)))
        self.stdout.write(
            "\nNext: spot-check ~15 records by hand before trusting the numbers, "
            "then run:\n"
            f"  python manage.py run_eval --tenant {options['tenant']} "
            f"--agent {agent.id}"
        )
