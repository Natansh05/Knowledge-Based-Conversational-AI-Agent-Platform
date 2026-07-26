# evaluation.trace
"""
Per-request timing / token / cache instrumentation.

The answer path takes an optional `trace` argument that is `None` in production
serving. Every call site uses the module-level `span()` helper, which returns a
no-op context manager when the trace is None, so an untraced request does no
bookkeeping beyond one `is None` check.

Nothing in here may raise: instrumentation must never break answering. Token
recording in particular parses provider-specific response metadata, which is not
guaranteed to be present on every response.
"""
import time
from contextlib import contextmanager


@contextmanager
def _null_span():
    yield


def span(trace, name):
    """
    Time a block into `trace`, or do nothing when `trace` is None.

        with span(trace, "retrieval"):
            ...

    Kept as a module-level function rather than a method so call sites don't
    need an `if trace is not None` guard around every stage.
    """
    if trace is None:
        return _null_span()
    return trace.span(name)


def record_tokens(trace, label, response):
    """Record an LLM call's token usage, or do nothing when `trace` is None."""
    if trace is None:
        return
    trace.record_tokens(label, response)


class QueryTrace:
    """
    Collects one query's timing and cost breakdown.

    Spans accumulate: calling `span("embed")` twice adds both durations, which is
    what we want when a stage runs once per sub-query.
    """

    def __init__(self):
        self.spans_ms = {}
        self.span_counts = {}
        self.tokens = {}
        self.cache_state = None
        self.meta = {}
        self._start = time.perf_counter()

    @contextmanager
    def span(self, name):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.spans_ms[name] = self.spans_ms.get(name, 0.0) + elapsed_ms
            self.span_counts[name] = self.span_counts.get(name, 0) + 1

    def record_tokens(self, label, response):
        """
        Pull token counts off a provider response.

        Gemini exposes `usage_metadata` with prompt/candidates/total counts. This
        is best-effort by design: a missing or renamed field costs us telemetry,
        never a user's answer.
        """
        try:
            usage = getattr(response, "usage_metadata", None)
            if usage is None:
                return
            bucket = self.tokens.setdefault(
                label, {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
            )
            bucket["prompt"] += getattr(usage, "prompt_token_count", 0) or 0
            bucket["completion"] += getattr(usage, "candidates_token_count", 0) or 0
            bucket["total"] += getattr(usage, "total_token_count", 0) or 0
            bucket["calls"] += 1
        except Exception:
            # Telemetry must never break the answer path.
            pass

    def record_cache(self, state):
        """state is one of: "hit", "miss", "skipped"."""
        self.cache_state = state

    def set(self, key, value):
        self.meta[key] = value

    @property
    def total_ms(self):
        return (time.perf_counter() - self._start) * 1000.0

    def token_totals(self):
        totals = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
        for bucket in self.tokens.values():
            for key in totals:
                totals[key] += bucket[key]
        return totals

    def to_dict(self):
        return {
            "total_ms": round(self.total_ms, 2),
            "spans_ms": {k: round(v, 2) for k, v in self.spans_ms.items()},
            "span_counts": dict(self.span_counts),
            "tokens": {k: dict(v) for k, v in self.tokens.items()},
            "token_totals": self.token_totals(),
            "cache_state": self.cache_state,
            "meta": dict(self.meta),
        }
