"""Offline sweep of the semantic-cache distance threshold.

For each paraphrase, find its nearest ORIGINAL question (candidate pool = only
originals that were actually cached, i.e. status 'high' in a prior run's
report.json). Report, per cosine-distance threshold, the hit rate and how many
of those hits map to the CORRECT original (same golden id) vs a false hit. This
locates the precision cliff before you raise SEMANTIC_CACHE_DISTANCE_THRESHOLD.

    uv run python evaluation/scripts/threshold_sweep.py \
        [--tenant test] \
        [--orig evaluation/dataset/golden_set.jsonl] \
        [--para evaluation/dataset/golden_set_paraphrased.jsonl] \
        [--report evaluation/reports/cache_orig/report.json]

Approximation: uses raw-question embeddings, whereas production matches on the
post-rewrite query. Rewriting normalises queries, so production distances differ
— confirm any chosen threshold with a live run (see example_threshold_tuning.md).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import django

BACKEND = Path(__file__).resolve().parents[2]
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np  # noqa: E402
from django_tenants.utils import schema_context  # noqa: E402

THRESHOLDS = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30]


def load(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        rec = json.loads(line)
        if "__meta__" not in rec:
            out[rec["id"]] = rec["question"]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="test")
    parser.add_argument("--orig", default="evaluation/dataset/golden_set.jsonl")
    parser.add_argument("--para",
                        default="evaluation/dataset/golden_set_paraphrased.jsonl")
    parser.add_argument("--report",
                        default="evaluation/reports/cache_orig/report.json")
    args = parser.parse_args()

    with schema_context(args.tenant):
        from rag.processors.embeddings import generate_embeddings

        originals = load(args.orig)
        paraphrases = load(args.para)

        # Candidate pool = only ids that were actually cached (grounded/high).
        report = json.load(open(args.report))
        cached_ids = [r["id"] for r in report["per_query"]
                      if r["status"] == "high" and r["id"] in originals]

        pool = np.array(generate_embeddings([originals[i] for i in cached_ids]))
        pool /= np.linalg.norm(pool, axis=1, keepdims=True)

        para_ids = list(paraphrases)
        pvecs = np.array(generate_embeddings([paraphrases[i] for i in para_ids]))
        pvecs /= np.linalg.norm(pvecs, axis=1, keepdims=True)

        sims = pvecs @ pool.T
        nearest = sims.argmax(axis=1)
        dist = 1.0 - sims.max(axis=1)
        rows = [(para_ids[k], cached_ids[nearest[k]], float(dist[k]),
                 para_ids[k] == cached_ids[nearest[k]])
                for k in range(len(para_ids))]

    n = len(rows)
    print(f"{n} paraphrase queries vs {len(cached_ids)} cached originals\n")
    print(f"{'thresh':>7} {'hits':>5} {'correct':>8} {'false':>6} "
          f"{'hit_rate':>9} {'precision':>10}")
    for t in THRESHOLDS:
        hits = [r for r in rows if r[2] <= t]
        correct = [r for r in hits if r[3]]
        prec = len(correct) / len(hits) if hits else float("nan")
        print(f"{t:>7.2f} {len(hits):>5} {len(correct):>8} "
              f"{len(hits) - len(correct):>6} {len(hits) / n:>9.3f} {prec:>10.3f}")


if __name__ == "__main__":
    main()
