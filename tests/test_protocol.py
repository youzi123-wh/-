"""Tests for leakage boundaries, metrics and persistent inference contracts."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gardenrec.data import load_dataset, user_holdout
from gardenrec.metrics import ranking_for_user, rating_metrics, evaluate_ranking
from gardenrec.models import Bias, ItemKNN, MFALS, GlobalMean, Popularity, save_model, load_model

TEST_TMP = Path(__file__).resolve().parents[1] / "tmp" / "tests"
TEST_TMP.mkdir(parents=True, exist_ok=True)

class DataProtocolTests(unittest.TestCase):
    def test_holdout_is_reproducible_disjoint_and_per_user(self):
        users = np.repeat(np.arange(4), [5, 6, 10, 1])
        indices = np.arange(len(users))
        train, test = user_holdout(users, indices, seed=42)
        fit, val = user_holdout(users, train, seed=43)
        np.testing.assert_array_equal(train, user_holdout(users, indices, seed=42)[0])
        self.assertEqual(set(train) & set(test), set())
        self.assertEqual(set(train) | set(test), set(indices))
        self.assertEqual(set(fit) | set(val), set(train))
        self.assertEqual(set(fit) & set(val), set())
        self.assertEqual(set(val) & set(test), set())
        self.assertEqual([int(np.sum(users[train] == u)) for u in range(4)], [4, 4, 8, 1])
        self.assertEqual([int(np.sum(users[test] == u)) for u in range(4)], [1, 2, 2, 0])

    def test_latest_duplicate_retained_and_source_unchanged(self):
        rows = [dict(reviewerID="u", asin="i", overall=1, unixReviewTime=20, reviewText="latest"),
                dict(reviewerID="u", asin="i", overall=5, unixReviewTime=10, reviewText="old")]
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            path = Path(temp) / "data.json"
            original = "\n".join(json.dumps(r) for r in rows)
            path.write_text(original, encoding="utf-8")
            data = load_dataset(path)
            self.assertEqual(data.duplicates_removed, 1)
            self.assertEqual(data.ratings.tolist(), [1])
            self.assertEqual(data.records[0]["reviewText"], "latest")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_invalid_rating_rejected_with_line_number(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"reviewerID":"u","asin":"i","overall":6}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r":1:"):
                load_dataset(path)


class MetricTests(unittest.TestCase):
    def test_hand_calculated_metrics(self):
        result = rating_metrics([1, 5], [2, 3])
        self.assertEqual(result["mae"], 1.5)
        self.assertAlmostEqual(result["rmse"], np.sqrt(2.5))
        rank = ranking_for_user([8, 9, 3], {8, 3}, k=3)
        self.assertAlmostEqual(rank["precision"], 2 / 3)
        self.assertEqual(rank["recall"], 1)
        self.assertAlmostEqual(rank["ndcg"], (1 + 1 / np.log2(4)) / (1 + 1 / np.log2(3)))
        self.assertEqual(ranking_for_user([1, 2], {3}, 2)["ndcg"], 0)

    def test_macro_f_measure_matches_course_definition(self):
        matrix = np.array([[5, 0, 0, 0], [5, 0, 0, 0]], dtype=float)
        model = GlobalMean().fit(matrix)
        agg, rows, _ = evaluate_ranking(model, np.array([0, 1, 1]), np.array([1, 1, 3]), k=2)
        self.assertAlmostEqual(agg["precision"], 0.5)
        self.assertAlmostEqual(agg["recall"], 0.75)
        self.assertAlmostEqual(agg["f_measure"], 0.6)
        self.assertNotEqual(agg["f_measure"], agg["macro_f1"])
        self.assertEqual(len(rows), 2)

    def test_invalid_or_duplicate_predictions_rejected(self):
        with self.assertRaises(ValueError):
            rating_metrics([1], [float("nan")])
        with self.assertRaises(ValueError):
            ranking_for_user([1, 1], {1}, 2)


class ModelContractTests(unittest.TestCase):
    def setUp(self):
        self.matrix = np.array([[5, 1, 0, 0, 0], [4, 0, 3, 0, 0], [0, 2, 5, 4, 0]], dtype=float)

    def test_recommendations_exclude_seen_and_roundtrip_is_identical(self):
        models = [GlobalMean(), Popularity(), Bias(), ItemKNN(neighbors=1),
                  MFALS(factors=2, epochs=5, factor_reg=2)]
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            for model in models:
                with self.subTest(model=type(model).__name__):
                    model.fit(self.matrix)
                    recs, scores = model.recommend(0, 10)
                    self.assertEqual(set(recs), {2, 3, 4})
                    self.assertTrue(np.all(np.isfinite(scores)))
                    path = Path(temp) / "model.npz"
                    params = ({"neighbors": 1} if isinstance(model, ItemKNN) else
                              {"factors": 2, "epochs": 5, "factor_reg": 2} if isinstance(model, MFALS) else {})
                    save_model(model, path, ["u0", "u1", "u2"], [str(i) for i in range(5)], params)
                    restored, _ = load_model(path)
                    np.testing.assert_array_equal(restored.recommend(0, 10)[0], recs)
                    np.testing.assert_allclose(restored.recommend(0, 10)[1], scores, rtol=0, atol=0)

    def test_rating_bounds_unknown_id_and_cold_item_fallback(self):
        for model in [Bias(), ItemKNN(), MFALS(factors=2, epochs=5)]:
            model.fit(self.matrix)
            pred = model.predict(np.array([0, 1, -1, 100]), np.array([4, 4, 0, 1]))
            self.assertTrue(np.all((1 <= pred) & (pred <= 5)))
            self.assertEqual(pred[-1], model.mean)
            self.assertEqual(pred[-2], model.mean)
            self.assertAlmostEqual(pred[0], model.mean + model.user_bias[0])

    def test_als_optimizes_observed_objective_monotonically(self):
        model = MFALS(factors=2, epochs=8, factor_reg=0.5).fit(self.matrix)
        self.assertTrue(np.all(np.diff(model.loss_history) <= 1e-9))
        self.assertTrue(np.all(model.item_factors[-1] == 0))

    def test_ties_have_stable_item_order(self):
        model = GlobalMean().fit(self.matrix)
        np.testing.assert_array_equal(model.recommend(0, 3)[0], [2, 3, 4])


if __name__ == "__main__":
    unittest.main()
