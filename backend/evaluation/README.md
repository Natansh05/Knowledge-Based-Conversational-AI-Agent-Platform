# RAG evaluation harness

A golden-dataset evaluation harness for the retrieval + answer pipeline:
custom ranking metrics (Recall/Precision/nDCG @k), routing/refusal metrics,
per-stage latency and token instrumentation, and Ragas answer-quality scores —
all measured against a golden set built from a tenant's own documents.

**Commands and full workflow:** see [`management/commands/usage.txt`](management/commands/usage.txt).
**Example output:** see [`examples/`](examples/).

## What is committed vs generated

| Path | Committed? | Why |
|---|---|---|
| `*.py`, `management/commands/usage.txt` | ✅ yes | Source of truth. |
| `README.md`, `examples/*` | ✅ yes | Docs + sanitized, metrics-only sample reports. |
| `reports/` | ❌ git-ignored | Generated run outputs. `eval_records.json` embeds **raw chunk text** from tenant documents. |
| `dataset/golden_set.jsonl` | ❌ git-ignored | Built from **private tenant content** (questions + ground-truth answers). Regenerate locally. |

The ignore rules live in the repo-root `.gitignore` under the
"RAG evaluation harness" heading.

### Why the golden set is not committed

It is the fixed reference point for comparing runs, so it is tempting to commit —
but it is derived from real documents and would leak their content. If your repo
is **private and the source documents are not sensitive**, you may choose to
commit it (remove the `.gitignore` line); then keep it frozen, because a
regenerated set is not comparable to the old one. Public repos: keep it ignored.

### Regenerating locally

```bash
uv sync --group eval
python manage.py build_golden_set --tenant <tenant> --agent <id> --sleep 2
python manage.py run_eval        --tenant <tenant> --agent <id>
python manage.py score_ragas
```

## Examples

- [`examples/example_report.md`](examples/example_report.md) — a full `run_eval`
  + `score_ragas` report (70 questions, ~103 chunks). Shows the reranker beating
  raw vector search (recall@5 0.54 → 0.66) and a high false-answer rate flagging
  over-permissive thresholds.
- [`examples/example_cache_comparison.md`](examples/example_cache_comparison.md) —
  a cold-vs-warm semantic-cache A/B (median latency 6.5s → 1.7s at an 82.8% hit
  rate), including why warm-run retrieval metrics must not be read as a
  regression.
- [`examples/example_threshold_tuning.md`](examples/example_threshold_tuning.md) —
  using the harness to change a config constant with evidence: an offline
  precision/recall sweep plus a live before/after that doubled the paraphrase
  cache-hit rate (30% → 63%) with no false hits.

These are sanitized (aggregate metrics only, tenant/agent scrubbed) so they are
safe to publish; the live `reports/` equivalents are not.

## Helper scripts

One-off analysis helpers under [`scripts/`](scripts/), runnable with
`uv run python evaluation/scripts/<name>`:

- `paraphrase_golden_set.py` — rewords a golden set (same meaning, different
  wording) to test whether the cache matches paraphrases, not just exact repeats.
- `threshold_sweep.py` — offline precision/recall sweep of the cache distance
  threshold; locates the false-hit cliff before you raise it.
