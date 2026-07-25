# evaluation.tests
"""
Unit tests for the ranking metrics.

Plain unittest with no Django or database dependency, so they can be run either
through `manage.py test evaluation` or directly with
`python -m unittest evaluation.tests`.
"""
import unittest

from evaluation.metrics.ranking import (
    aggregate,
    evaluate_ranking,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class RecallTests(unittest.TestCase):
    def test_recall_is_fraction_of_relevant_found(self):
        ranked = [10, 20, 30, 40]
        relevant = {10: 2, 20: 1, 30: 1}

        self.assertAlmostEqual(recall_at_k(ranked, relevant, 1), 1 / 3)
        self.assertAlmostEqual(recall_at_k(ranked, relevant, 3), 1.0)
        self.assertAlmostEqual(recall_at_k(ranked, relevant, 5), 1.0)

    def test_grade_zero_labels_are_not_relevant(self):
        # An explicit 0 grade is a judged-irrelevant chunk, not a relevant one.
        self.assertIsNone(recall_at_k([10], {10: 0}, 1))

    def test_no_relevant_chunks_is_undefined_not_zero(self):
        # Out-of-scope golden records land here. Returning 0.0 instead of None
        # would let the dataset's out-of-scope share depress the corpus mean.
        self.assertIsNone(recall_at_k([10, 20], {}, 5))


class PrecisionTests(unittest.TestCase):
    def test_precision_divides_by_k(self):
        ranked = [10, 20, 30, 40, 50]
        relevant = {10: 2, 20: 1}

        self.assertAlmostEqual(precision_at_k(ranked, relevant, 1), 1.0)
        self.assertAlmostEqual(precision_at_k(ranked, relevant, 3), 2 / 3)
        # The documented ceiling: only 2 relevant chunks exist, so P@5 <= 0.4.
        self.assertAlmostEqual(precision_at_k(ranked, relevant, 5), 2 / 5)

    def test_no_relevant_chunks_is_undefined(self):
        self.assertIsNone(precision_at_k([10], {}, 1))


class NDCGTests(unittest.TestCase):
    def test_perfect_ordering_scores_one(self):
        ranked = [10, 20, 30]
        relevant = {10: 2, 20: 1, 30: 1}
        self.assertAlmostEqual(ndcg_at_k(ranked, relevant, 5), 1.0)

    def test_perfect_ordering_scores_one_when_k_exceeds_results(self):
        self.assertAlmostEqual(ndcg_at_k([10], {10: 2}, 10), 1.0)

    def test_worse_ordering_scores_lower(self):
        relevant = {10: 2, 20: 1, 30: 1}
        best = ndcg_at_k([10, 20, 30], relevant, 5)
        worst = ndcg_at_k([30, 20, 10], relevant, 5)
        self.assertGreater(best, worst)
        # Hand-computed with exponential gains (2^g - 1):
        #   actual = 1/log2(2) + 1/log2(3) + 3/log2(4) = 3.13093
        #   ideal  = 3/log2(2) + 1/log2(3) + 1/log2(4) = 4.13093
        self.assertAlmostEqual(worst, 3.13093 / 4.13093, places=5)

    def test_graded_labels_beat_binary_ordering(self):
        # The grade-2 chunk ranked first must outscore the grade-1 chunk first.
        relevant = {10: 2, 20: 1}
        self.assertGreater(
            ndcg_at_k([10, 20], relevant, 5),
            ndcg_at_k([20, 10], relevant, 5),
        )

    def test_no_relevant_chunks_is_undefined(self):
        self.assertIsNone(ndcg_at_k([10, 20], {}, 5))


class AggregateTests(unittest.TestCase):
    def test_undefined_scores_are_excluded_and_counted(self):
        in_scope = evaluate_ranking([10, 20], {10: 2, 20: 1})
        out_of_scope = evaluate_ranking([30, 40], {})

        result = aggregate([in_scope, out_of_scope])

        # Only the in-scope query contributes, and n records that fact.
        self.assertEqual(result["recall@1"]["n"], 1)
        self.assertAlmostEqual(result["recall@1"]["mean"], 0.5)
        self.assertEqual(result["ndcg@5"]["n"], 1)

    def test_mean_across_queries(self):
        a = {"recall@1": 1.0}
        b = {"recall@1": 0.0}
        result = aggregate([a, b])
        self.assertAlmostEqual(result["recall@1"]["mean"], 0.5)
        self.assertEqual(result["recall@1"]["n"], 2)


if __name__ == "__main__":
    unittest.main()
