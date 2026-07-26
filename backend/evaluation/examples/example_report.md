# RAG Evaluation Report

<!--
Sanitized example output of `manage.py run_eval` followed by `manage.py
score_ragas`. Produced against a 3-document / ~103-chunk agent with a
70-question golden set. Metrics only — no document text. The real report.md
lives in evaluation/reports/ and is git-ignored.
-->

- tenant: `<tenant>`  agent: `<id>`
- golden set: `evaluation/dataset/golden_set.jsonl` (70 records)
- semantic cache: disabled

## Retrieval ranking

| metric | ann | rerank |
|---|---|---|
| ndcg@10 | 0.636 (n=55) | 0.736 (n=55) |
| ndcg@5 | 0.602 (n=55) | 0.722 (n=55) |
| precision@1 | 0.745 (n=55) | 0.873 (n=55) |
| precision@3 | 0.558 (n=55) | 0.721 (n=55) |
| precision@5 | 0.458 (n=55) | 0.589 (n=55) |
| recall@1 | 0.221 (n=55) | 0.261 (n=55) |
| recall@3 | 0.431 (n=55) | 0.546 (n=55) |
| recall@5 | 0.536 (n=55) | 0.663 (n=55) |

`ann` is the pgvector candidate order; `rerank` is after the cross-encoder. A rerank column that does not beat ann means the cross-encoder is not earning its place on the critical path.

Metrics are computed over the full pre-truncation candidate list. The served answer uses at most 4 chunks (usually 2), so @5 and @10 are undefined on the delivered set.

### Recall@5 by query type

| query type | n | recall@5 |
|---|---|---|
| multi_part | 15 | 0.517 |
| negation | 10 | 0.329 |
| out_of_scope | 0 | — |
| single_hop | 30 | 0.847 |

## Routing behaviour

- **correct refusal rate**: 0.133 (n=15 out-of-scope)
- **false answer rate**: 0.867 — out-of-scope questions that got a grounded answer
- clarified instead: 0.000
- **missed answer rate**: 0.073 — answerable questions the system refused (n=55)

### Expected vs actual status

| expected | high | low |
|---|---|---|
| high | 51 | 4 |
| low | 13 | 2 |

## Application metrics

### Latency (ms, p50 / p95)

| stage | p50 / p95 |
|---|---|
| total_ms | 6251 / 11351 |
| rewrite | 1329 / 1730 |
| embed | 349 / 1193 |
| ann_fetch | 17 / 37 |
| rerank | 228 / 706 |
| retrieval_derived_ms | 571 / 1405 |
| generation | 4093 / 8889 |
| cache_lookup | 0 / 0 |
| cache_store | 0 / 0 |
| guardrail | 0 / 0 |

### Tokens

| call site | calls | prompt | completion | total |
|---|---|---|---|---|
| fallback | 6 | 2474 | 1816 | 7867 |
| generation | 64 | 42150 | 12301 | 90582 |
| rewrite | 70 | 25541 | 5711 | 31252 |

Mean 1853 tokens per query (129701 total).

### Cache

- states: `{'miss': 59, 'skipped': 11}`
- hit rate: 0.000

> Hit rate from an eval run is meaningless — the cache is disabled so results are reproducible. Measure it from serving traffic instead.

## Ragas

| metric | mean | n |
|---|---|---|
| answer_correctness | 0.460 | 40 |
| context_precision | 0.812 | 40 |
| context_recall | 0.854 | 40 |
| faithfulness | 0.966 | 40 |

## Caveats

- n=70: confidence intervals are wide. Treat differences under ~5 points as noise.
- Supporting labels come from the same cross-encoder the pipeline uses to rerank, so retrieval metrics are mildly flattering to that reranker.
- Ragas metrics are LLM-judged and vary between runs on identical input.
