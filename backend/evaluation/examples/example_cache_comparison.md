# Semantic Cache A/B — Example

<!--
Sanitized example of a two-pass cache measurement. Both passes run the SAME
70-question golden set through `run_eval --keep-cache`, writing to separate
--out dirs:

    run_eval --tenant <t> --agent <id> --keep-cache --out reports/cache_cold
    run_eval --tenant <t> --agent <id> --keep-cache --out reports/cache_warm

Pass 1 (cold) starts with an empty cache and populates it. Pass 2 (warm) asks
the identical questions, so they hit the cache. This measures the exact-repeat
upper bound, not paraphrase robustness. Metrics only — no document text.
-->

## Headline

| | cold (pass 1) | warm (pass 2) | change |
|---|---|---|---|
| cache hit rate | 0.000 | **0.828** | 48 hit / 10 miss / 12 skipped |
| **total latency p50 (ms)** | 6525 | **1690** | **−74%** |
| generation LLM calls | 62 | **15** | −76% |
| total tokens | 140,449 | **61,103** | −56% |
| mean tokens / query | 2006 | 873 | −56% |

## Latency breakdown (ms, p50 / p95)

| stage | cold | warm |
|---|---|---|
| total_ms | 6525 / 17344 | 1690 / 12128 |
| rewrite | 1338 / 1818 | 1319 / 1803 |
| embed | 219 / 614 | 129 / 692 |
| ann_fetch | 15 / 28 | 16 / 33 |
| rerank | 232 / 662 | 226 / 894 |
| generation | 4273 / 12877 | 3971 / 10467 |
| cache_lookup | 7 / 13 | 10 / 21 |
| cache_store | 17 / 32 | 19 / 25 |

## Reading the numbers

**The cache saves retrieval + generation, not the rewrite.** The warm median is
~1.7s, not the ~30ms of a raw cache lookup, because `rewrite` (~1.3s) runs
*before* the cache lookup in the pipeline and fires on every request — note the
70 rewrite calls in both passes. The hit path is roughly
`rewrite + embed + cache_lookup ≈ 1.5s`. Moving the lookup ahead of the rewrite
would collapse hits toward the cache_lookup floor.

**Do NOT read the warm run's retrieval or refusal metrics as a regression.** On a
cache hit the pipeline returns the stored answer and skips retrieval entirely,
so `ranked_chunk_ids` is empty and `status` is `unknown` for the hit queries.
That structurally drives recall/precision toward zero and inflates
missed-answer-rate in the warm report — an artifact of hits bypassing
retrieval, not a quality change.

**Rule:** read retrieval quality from the cold run (cache empty → retrieval ran);
read latency / cost / hit-rate from the warm run. Never mix the two. This is why
`run_eval` disables the cache by default.

## Caveat

Exact-repeat questions are the easy case — they would hit even a string-keyed
cache. To show the cache is genuinely *semantic*, warm it with the original set
and then run a paraphrased copy of the questions; the hit rate on that run is the
honest measure of semantic matching.
