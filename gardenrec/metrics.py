"""Rating metrics and full-catalog, user-macro-averaged ranking metrics."""
import numpy as np


def rating_metrics(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    if not actual.size or actual.shape != predicted.shape:
        raise ValueError("Ratings and predictions must be nonempty and have the same shape")
    if not (np.all(np.isfinite(actual)) and np.all(np.isfinite(predicted))):
        raise ValueError("Metrics require finite values")
    error = actual - predicted
    return {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error**2)))}


def ranking_for_user(recommended, relevant, k=10):
    if k < 1 or not relevant:
        raise ValueError("Positive k and nonempty relevant set are required")
    recommended = list(recommended)[:k]
    if len(set(recommended)) != len(recommended):
        raise ValueError("Recommendation lists must not contain duplicates")
    hits = np.array([item in relevant for item in recommended], dtype=float)
    precision = float(hits.sum() / k)
    recall = float(hits.sum() / len(relevant))
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    discount = 1 / np.log2(np.arange(2, len(hits) + 2))
    ideal = float(np.sum(1 / np.log2(np.arange(2, min(k, len(relevant)) + 2))))
    return {"precision": precision, "recall": recall, "f1_user": f1,
            "ndcg": float(hits @ discount / ideal), "hits": int(hits.sum())}


def evaluate_ranking(model, users, items, k=10):
    per_user, recommendations = [], []
    for user in np.unique(users):
        relevant = set(items[users == user].tolist())
        recs, scores = model.recommend(int(user), k)
        metrics = ranking_for_user(recs.tolist(), relevant, k)
        per_user.append({"user_index": int(user), "relevant_count": len(relevant), **metrics})
        recommendations.append((int(user), recs, scores))
    if not per_user:
        raise ValueError("No users with held-out items")
    aggregate = {key: float(np.mean([m[key] for m in per_user]))
                 for key in ("precision", "recall", "ndcg")}
    p, r = aggregate["precision"], aggregate["recall"]
    # The assignment defines F from macro Precision and macro Recall.
    aggregate["f_measure"] = 2 * p * r / (p + r) if p + r else 0.0
    aggregate["macro_f1"] = float(np.mean([m["f1_user"] for m in per_user]))
    aggregate["evaluated_users"] = len(per_user)
    aggregate["catalog_coverage"] = len({int(i) for _, recs, _ in recommendations for i in recs}) / model.n_items
    return aggregate, per_user, recommendations
