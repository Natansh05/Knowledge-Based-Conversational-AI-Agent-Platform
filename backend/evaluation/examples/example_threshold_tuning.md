# Semantic Cache Threshold Tuning — Example

<!--
End-to-end example of using the harness to change a config constant with
evidence. Sanitized: aggregate metrics only, no document text. The workflow was:
generate a paraphrased golden set -> sweep the threshold offline to find where
false hits begin -> pick a value -> confirm on the live pipeline.
-->

## The problem

`SEMANTIC_CACHE_DISTANCE_THRESHOLD` (cosine distance ceiling for a cache hit)
was `0.08` with no evidence behind it — a strict value that only catches
near-exact repeats. Question: can we raise it to catch paraphrases too, without
serving a *wrong* cached answer (a false hit)?

## Step 1 — Measure the baseline (paraphrase hit rate at 0.08)

Warm the cache with the original questions, then run a paraphrased copy of the
same 70 questions through the live pipeline:

```bash
uv run python evaluation/scripts/paraphrase_golden_set.py     # make the paraphrase set
# clear cache, then:
uv run python manage.py run_eval --tenant test --agent 1 --keep-cache \
    --out evaluation/reports/cache_orig                        # populate (originals)
uv run python manage.py run_eval --tenant test --agent 1 --keep-cache \
    --golden evaluation/dataset/golden_set_paraphrased.jsonl \
    --out evaluation/reports/cache_para                         # measure (paraphrases)
```

Result: **29.8% hit rate** (17 hit / 40 miss / 13 skipped). So the cache is
genuinely semantic — a string cache would score 0% on rewordings — but strict.

## Step 2 — Offline sweep to find the precision cliff

`threshold_sweep.py` computes, for each paraphrase, the distance to its nearest
cached original and whether that nearest match is the *correct* question:

```bash
uv run python evaluation/scripts/threshold_sweep.py
```

```
 thresh  hits  correct  false  hit_rate  precision
   0.08    32       32      0     0.457      1.000
   0.10    44       44      0     0.629      1.000
   0.12    49       49      0     0.700      1.000
   0.15    54       54      0     0.771      1.000
   0.18    57       57      0     0.814      1.000
   0.20    59       59      0     0.843      1.000
   0.25    62       62      0     0.886      1.000
   0.30    62       62      0     0.886      1.000
```

Precision stays **1.000 up to 0.30** on this data — no false hits — while recall
climbs. (Absolute hit rates here are higher than the live numbers because this
sweep matches raw questions, whereas production matches the post-rewrite query;
the *shape* is the signal.) Chosen value: **0.15** — a moderate 2x step, kept
conservative because the zero-false-hit margin is partly a property of a small,
topically-distinct question set.

## Step 3 — Confirm on the live pipeline at 0.15

Re-ran the same populate + paraphrase measure with the new threshold:

| paraphrase run | hit rate | generation calls | total latency p50 |
|---|---|---|---|
| threshold 0.08 (before) | 29.8% | 40 | 5625 ms |
| **threshold 0.15 (after)** | **63.2%** | **21** | **4237 ms** |

**The paraphrase hit rate more than doubled (30% -> 63%)** with no false hits.
Because more queries skip generation, median latency fell ~1.4s and generation
LLM calls nearly halved.

## Outcome

`config/settings.py` default changed `0.08 -> 0.15`, with the rationale recorded
inline. Caveats carried forward:

- The zero-false-hit margin is dataset-specific; on real traffic with many
  similar questions, false hits can appear below 0.15 — monitor in production.
- Cache-hit latency is still floored (~1.3s) by the query-rewrite LLM call that
  runs *before* the cache lookup; moving the lookup ahead of rewrite is a
  separate optimization.
