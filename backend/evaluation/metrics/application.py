# evaluation.metrics.application
"""
Aggregation of the per-query QueryTrace dicts: latency, tokens, cache.

Latency is reported as median and p95 rather than a mean. The pipeline's cost is
dominated by two LLM round-trips (the rewriter and the answer) plus a
cross-encoder pass, all of which have long tails; a mean hides exactly the
behaviour worth knowing about.

A note on cache hit rate: an eval run is expected to execute with
SEMANTIC_CACHE_ENABLED=False, so its hit rate is meaningless by construction and
this module will report it as such. Production hit rate has to come from serving
traffic, not from here.
"""

# Spans that together constitute retrieval. Spans are recorded leaf-only — no
# span contains another — so that the recorded durations sum to roughly the
# wall-clock total. That makes retrieval a derived figure rather than its own
# span.
RETRIEVAL_SPANS = ("embed", "ann_fetch", "rerank")


def percentile(values, fraction):
    """Nearest-rank percentile. Returns None for an empty input."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def _stats(values):
    if not values:
        return None
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def aggregate_traces(traces):
    """
    `traces` is a list of QueryTrace.to_dict() outputs.
    """
    if not traces:
        return {}

    span_names = sorted({name for t in traces for name in t.get("spans_ms", {})})

    latency = {"total_ms": _stats([t["total_ms"] for t in traces])}
    for name in span_names:
        # A span missing from a trace means that stage did not run for that query
        # (a refused query never generates, a cache hit never retrieves). Those
        # are excluded rather than counted as zero, so "rerank p50" means the p50
        # of queries that actually reranked.
        values = [t["spans_ms"][name] for t in traces if name in t.get("spans_ms", {})]
        latency[name] = _stats(values)

    retrieval_totals = []
    for trace in traces:
        spans = trace.get("spans_ms", {})
        present = [spans[name] for name in RETRIEVAL_SPANS if name in spans]
        if present:
            retrieval_totals.append(sum(present))
    latency["retrieval_derived_ms"] = _stats(retrieval_totals)

    # Tokens, split by call site: the rewriter runs on every request and is easy
    # to overlook when only the answer call is measured.
    token_labels = sorted({label for t in traces for label in t.get("tokens", {})})
    tokens = {}
    for label in token_labels:
        buckets = [t["tokens"][label] for t in traces if label in t.get("tokens", {})]
        tokens[label] = {
            "calls": sum(b["calls"] for b in buckets),
            "prompt": sum(b["prompt"] for b in buckets),
            "completion": sum(b["completion"] for b in buckets),
            "total": sum(b["total"] for b in buckets),
        }
    total_tokens = sum(t.get("token_totals", {}).get("total", 0) for t in traces)
    tokens["_all"] = {
        "total": total_tokens,
        "mean_per_query": total_tokens / len(traces),
    }

    cache_states = {}
    for trace in traces:
        state = trace.get("cache_state") or "not_recorded"
        cache_states[state] = cache_states.get(state, 0) + 1

    hits = cache_states.get("hit", 0)
    considered = hits + cache_states.get("miss", 0)
    cache = {
        "states": cache_states,
        # Excludes "skipped" (exclusion queries bypass the cache by design);
        # counting a deliberate bypass as a miss would understate the rate.
        "hit_rate": (hits / considered) if considered else None,
    }

    return {"latency_ms": latency, "tokens": tokens, "cache": cache,
            "queries": len(traces)}
