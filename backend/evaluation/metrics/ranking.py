# evaluation.metrics.ranking
"""
Deterministic retrieval-ranking metrics.

Deliberately dependency-free (no numpy, no Django) so the unit tests run in
milliseconds without a database or an LLM.

Two conventions worth stating, because they change how the numbers read:

* **Undefined, not zero.** A query with no relevant chunks — every out-of-scope
  record in the golden set — has undefined recall and nDCG. These functions
  return None so the aggregator can exclude them. Scoring them as 0.0 would drag
  the corpus average down in proportion to how many out-of-scope queries the set
  contains, which is a property of the dataset, not of retrieval.

* **Precision@k divides by k**, the standard definition, even when fewer than k
  results were retrieved. Metrics are computed over the full reranked candidate
  list (20-100 chunks), so this only bites on tiny corpora.
"""
from math import log2

DEFAULT_KS = (1, 3, 5)
DEFAULT_NDCG_KS = (5, 10)


def _relevant_ids(relevant):
    """Chunk ids with a grade above zero."""
    return {cid for cid, grade in relevant.items() if grade > 0}


def recall_at_k(ranked, relevant, k):
    """
    Fraction of the query's relevant chunks that appear in the top k.

    `ranked` is a list of chunk ids in rank order; `relevant` maps chunk id to a
    graded relevance (0 = irrelevant, 1 = supporting, 2 = fully answers).
    Returns None when the query has no relevant chunks.
    """
    truth = _relevant_ids(relevant)
    if not truth:
        return None
    hits = sum(1 for cid in ranked[:k] if cid in truth)
    return hits / len(truth)


def precision_at_k(ranked, relevant, k):
    """
    Fraction of the top k that is relevant. Returns None when the query has no
    relevant chunks, matching recall so both are excluded from the same records.

    Note the ceiling: with only 1-3 relevant chunks per query, Precision@5 cannot
    exceed 0.2-0.6. Read Precision@1 and Recall@k as the real signals.
    """
    truth = _relevant_ids(relevant)
    if not truth:
        return None
    if k <= 0:
        return None
    hits = sum(1 for cid in ranked[:k] if cid in truth)
    return hits / k


def _gain(grade, exponential):
    return (2 ** grade) - 1 if exponential else grade


def _dcg(grades, exponential):
    return sum(
        _gain(grade, exponential) / log2(rank + 2)
        for rank, grade in enumerate(grades)
    )


def ndcg_at_k(ranked, relevant, k, exponential=True):
    """
    Normalised discounted cumulative gain over graded relevance.

    Uses the exponential gain 2^g - 1 by default, so a grade-2 chunk is worth
    three times a grade-1 chunk rather than twice. With purely binary labels the
    two forms coincide up to a constant and nDCG degenerates toward a smoothed
    recall — which is why the golden set grades seed chunks 2 and adjudicated
    chunks 1.

    Returns None when the query has no relevant chunks.
    """
    if not _relevant_ids(relevant):
        return None

    actual = [relevant.get(cid, 0) for cid in ranked[:k]]
    ideal = sorted(relevant.values(), reverse=True)[:k]

    idcg = _dcg(ideal, exponential)
    if idcg == 0:
        return None
    return _dcg(actual, exponential) / idcg


def evaluate_ranking(ranked, relevant, ks=DEFAULT_KS, ndcg_ks=DEFAULT_NDCG_KS):
    """All ranking metrics for one query, keyed by metric name."""
    scores = {}
    for k in ks:
        scores[f"recall@{k}"] = recall_at_k(ranked, relevant, k)
        scores[f"precision@{k}"] = precision_at_k(ranked, relevant, k)
    for k in ndcg_ks:
        scores[f"ndcg@{k}"] = ndcg_at_k(ranked, relevant, k)
    return scores


def aggregate(per_query_scores):
    """
    Mean each metric across queries, skipping None (undefined) values.

    Reports the contributing count alongside each mean, because metrics are
    averaged over different subsets — out-of-scope queries drop out of every
    ranking metric — and a mean over 55 records should not be silently compared
    against one over 70.
    """
    totals = {}
    for scores in per_query_scores:
        for name, value in scores.items():
            if value is None:
                continue
            bucket = totals.setdefault(name, {"sum": 0.0, "n": 0})
            bucket["sum"] += value
            bucket["n"] += 1

    return {
        name: {"mean": bucket["sum"] / bucket["n"], "n": bucket["n"]}
        for name, bucket in sorted(totals.items())
    }
