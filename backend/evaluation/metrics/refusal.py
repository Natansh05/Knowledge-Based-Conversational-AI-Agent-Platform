# evaluation.metrics.refusal
"""
Routing-behaviour metrics.

These exist to keep a threshold sweep honest. Recall@k alone can always be
improved by lowering TOP_SIMILARITY_THRESHOLD until everything is retrieved; what
that actually does is destroy the system's ability to say "I don't know". The
false-answer rate is the counterweight — the two must be read together.

The pipeline has three observable outcomes, and conflating them loses the point:

  answered   status "high" with chunks -> a grounded answer
  clarified  status "partial"/"ambiguous" -> a clarifying question, not an answer
  refused    status "low", "high" with no chunks, or guardrail-blocked

`clarified` is deliberately its own bucket. For an out-of-scope question it is
neither a correct refusal nor a false answer: the system hedged. Folding it into
either would flatter or punish the thresholds unfairly.
"""

ANSWERED = "answered"
CLARIFIED = "clarified"
REFUSED = "refused"


def classify_outcome(status, chunk_ids):
    if status == "blocked":
        return REFUSED
    if status in ("partial", "ambiguous"):
        return CLARIFIED
    if status == "high" and chunk_ids:
        return ANSWERED
    # "low", or "high" with an empty selection after the top_k/MIN_CHUNK_SCORE
    # filters — both route to the fallback LLM.
    return REFUSED


def evaluate_refusal(results):
    """
    `results` is a list of dicts with keys: query_type, expected_status, status,
    chunk_ids. Returns rates split by whether the query was answerable.
    """
    out_of_scope = [r for r in results if r["query_type"] == "out_of_scope"]
    in_scope = [r for r in results if r["query_type"] != "out_of_scope"]

    def rates(records):
        if not records:
            return {"n": 0}
        counts = {ANSWERED: 0, CLARIFIED: 0, REFUSED: 0}
        for record in records:
            counts[classify_outcome(record["status"], record.get("chunk_ids") or [])] += 1
        total = len(records)
        return {
            "n": total,
            "answered": counts[ANSWERED] / total,
            "clarified": counts[CLARIFIED] / total,
            "refused": counts[REFUSED] / total,
            "counts": counts,
        }

    out_rates = rates(out_of_scope)
    in_rates = rates(in_scope)

    summary = {
        "out_of_scope": out_rates,
        "in_scope": in_rates,
    }

    if out_rates["n"]:
        # The headline pair. correct_refusal should be high; false_answer is the
        # cost side of any threshold change that improves recall.
        summary["correct_refusal_rate"] = out_rates["refused"]
        summary["false_answer_rate"] = out_rates["answered"]
    if in_rates["n"]:
        # An answerable question the system refused: a miss.
        summary["missed_answer_rate"] = in_rates["refused"]

    return summary


def status_confusion(results):
    """
    expected_status -> actual status -> count.

    This is the direct evidence for the eight hand-tuned constants in
    rag/processors/retriever.py: it shows which zone each query actually landed
    in versus where it belonged.
    """
    matrix = {}
    for record in results:
        expected = record.get("expected_status", "unknown")
        actual = record.get("status", "unknown")
        matrix.setdefault(expected, {})
        matrix[expected][actual] = matrix[expected].get(actual, 0) + 1
    return matrix
