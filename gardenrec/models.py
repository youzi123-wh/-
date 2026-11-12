"""NumPy implementations. Zero entries mean missing, never a zero-star rating."""
from pathlib import Path
import json

import numpy as np


class Recommender:
    def fit(self, matrix):
        self.seen = matrix > 0
        self.n_users, self.n_items = matrix.shape
        self.mean = float(matrix[self.seen].mean())
        return self

    def predict(self, users, items):
        """Bound rating predictions, with unknown-ID fallback to training mean."""
        users, items = np.broadcast_arrays(np.asarray(users), np.asarray(items))
        out = np.full(users.shape, self.mean, dtype=float)
        valid = (users >= 0) & (users < self.n_users) & (items >= 0) & (items < self.n_items)
        for user in np.unique(users[valid]):
            selected = valid & (users == user)
            out[selected] = self.rating_scores(int(user))[items[selected]]
        return np.clip(out, 1, 5)

    def rating_scores(self, user):
        return self.scores(user)

    def recommend(self, user, k=10):
        if k < 1:
            raise ValueError("k must be positive")
        scores = self.scores(user).copy()
        if not np.all(np.isfinite(scores)):
            raise ValueError("Model produced nonfinite ranking scores")
        candidates = np.flatnonzero(~self.seen[user])
        # Stable tie-break is item index, corresponding to lexicographically sorted ASIN.
        order = np.lexsort((candidates, -scores[candidates]))[:k]
        return candidates[order], scores[candidates[order]]


class GlobalMean(Recommender):
    def __init__(self):
        pass

    def scores(self, user):
        return np.full(self.n_items, self.mean)


class Popularity(Recommender):
    """Ranking-only comparator. Scores are counts, not predicted stars."""
    def __init__(self):
        pass

    def fit(self, matrix):
        super().fit(matrix)
        self.counts = self.seen.sum(axis=0).astype(float)
        return self

    def scores(self, user):
        return self.counts.copy()


class Bias(Recommender):
    """Squared error + reg*(sum user_bias^2 + sum item_bias^2)."""
    def __init__(self, reg=15.0, iterations=20):
        self.reg, self.iterations = reg, iterations

    def fit(self, matrix):
        super().fit(matrix)
        self.user_bias = np.zeros(self.n_users)
        self.item_bias = np.zeros(self.n_items)
        for _ in range(self.iterations):
            self.user_bias = np.sum(np.where(self.seen,
                matrix - self.mean - self.item_bias[None, :], 0), axis=1) / (
                    self.seen.sum(axis=1) + self.reg)
            self.item_bias = np.sum(np.where(self.seen,
                matrix - self.mean - self.user_bias[:, None], 0), axis=0) / (
                    self.seen.sum(axis=0) + self.reg)
        return self

    def scores(self, user):
        return self.mean + self.user_bias[user] + self.item_bias


class ItemKNN(Bias):
    """Cosine of baseline residuals with co-rating shrinkage.

    Top-k POSITIVE neighbors are selected among the items a user rated, for
    each target. This avoids discarding useful neighbors globally. Missing
    neighbor predictions use the fitted baseline.
    """
    def __init__(self, neighbors=30, shrinkage=20.0, reg=15.0):
        super().__init__(reg=reg)
        self.neighbors, self.shrinkage = neighbors, shrinkage

    def fit(self, matrix):
        super().fit(matrix)
        self.residuals = np.where(self.seen,
            matrix - self.mean - self.user_bias[:, None] - self.item_bias[None, :], 0)
        norms = np.linalg.norm(self.residuals, axis=0)
        denom = norms[:, None] * norms[None, :]
        co_count = self.seen.astype(float).T @ self.seen.astype(float)
        self.similarity = np.divide(self.residuals.T @ self.residuals, denom,
            out=np.zeros_like(denom), where=denom > 0)
        self.similarity *= co_count / (co_count + self.shrinkage)
        self.similarity = np.maximum(self.similarity, 0)
        np.fill_diagonal(self.similarity, 0)
        return self

    def scores(self, user):
        history = np.flatnonzero(self.seen[user])
        if not len(history):
            return super().scores(user)
        weights = self.similarity[:, history].copy()
        if len(history) > self.neighbors:
            keep = np.argsort(-weights, axis=1, kind="stable")[:, :self.neighbors]
            mask = np.zeros_like(weights, dtype=bool)
            np.put_along_axis(mask, keep, True, axis=1)
            weights *= mask
        den = weights.sum(axis=1)
        adjustment = np.divide(weights @ self.residuals[user, history], den,
            out=np.zeros(self.n_items), where=den > 0)
        return super().scores(user) + adjustment


class MFALS(Bias):
    """Explicit-feedback ALS on observed baseline residuals only.

    The bias baseline is fitted first and held fixed. Minimize
    sum_observed (r_ui - mu - b_u - b_i - p_u.q_i)^2
    + factor_reg*(||P||^2 + ||Q||^2). This is not implicit-feedback ALS.
    """
    def __init__(self, factors=16, factor_reg=10.0, epochs=20, reg=15.0, seed=42):
        super().__init__(reg=reg)
        self.factors, self.factor_reg, self.epochs, self.seed = factors, factor_reg, epochs, seed

    def fit(self, matrix):
        super().fit(matrix)
        rng = np.random.default_rng(self.seed)
        self.user_factors = rng.normal(0, 0.1, (self.n_users, self.factors))
        self.item_factors = rng.normal(0, 0.1, (self.n_items, self.factors))
        residual = matrix - self.mean - self.user_bias[:, None] - self.item_bias[None, :]
        user_hist = [np.flatnonzero(row) for row in self.seen]
        item_hist = [np.flatnonzero(row) for row in self.seen.T]
        penalty = self.factor_reg * np.eye(self.factors)
        self.loss_history = []
        for _ in range(self.epochs):
            for user, items in enumerate(user_hist):
                q = self.item_factors[items]
                self.user_factors[user] = np.linalg.solve(q.T @ q + penalty, q.T @ residual[user, items])
            for item, users in enumerate(item_hist):
                p = self.user_factors[users]
                self.item_factors[item] = np.linalg.solve(p.T @ p + penalty, p.T @ residual[users, item])
            ui, ii = np.nonzero(self.seen)
            err = residual[ui, ii] - np.sum(self.user_factors[ui] * self.item_factors[ii], axis=1)
            self.loss_history.append(float(err @ err + self.factor_reg * (
                np.sum(self.user_factors**2) + np.sum(self.item_factors**2))))
        return self

    def scores(self, user):
        return super().scores(user) + self.item_factors @ self.user_factors[user]


MODELS = {c.__name__: c for c in (GlobalMean, Popularity, Bias, ItemKNN, MFALS)}


def make_model(name, params=None):
    return MODELS[name](**(params or {}))


def save_model(model, path, user_ids, item_ids, params=None):
    """Portable numerical arrays and JSON metadata, never pickle."""
    state = {key: value for key, value in vars(model).items() if isinstance(value, np.ndarray)}
    scalars = {key: value for key, value in vars(model).items()
               if isinstance(value, (int, float, str, list))}
    state["metadata"] = np.array(json.dumps({"model": type(model).__name__, "params": params or {},
        "scalars": scalars, "user_ids": user_ids, "item_ids": item_ids}))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **state)


def load_model(path):
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata"]))
        model = make_model(metadata["model"], metadata["params"])
        for key, value in metadata["scalars"].items():
            setattr(model, key, value)
        for key in archive.files:
            if key != "metadata":
                setattr(model, key, archive[key].copy())
    return model, metadata
