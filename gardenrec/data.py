"""Validated JSONL loading and reproducible, per-user holdout splits."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math

import numpy as np


@dataclass
class Dataset:
    records: list
    user_ids: list
    item_ids: list
    users: np.ndarray
    items: np.ndarray
    ratings: np.ndarray
    source_sha256: str
    duplicates_removed: int


def load_dataset(path):
    """Keep the most recent record for a user/item pair (last line breaks ties)."""
    path = Path(path)
    pairs = {}
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for line_no, line in enumerate(stream, 1):
            digest.update(line)
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                user, item = row["reviewerID"], row["asin"]
                rating = float(row["overall"])
                timestamp = int(row.get("unixReviewTime", 0))
                if (not isinstance(user, str) or not user.strip()
                        or not isinstance(item, str) or not item.strip()
                        or not np.isfinite(rating) or rating not in (1, 2, 3, 4, 5)):
                    raise ValueError("IDs must be nonempty strings and ratings integers in [1, 5]")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid record at {path}:{line_no}: {exc}") from exc
            count += 1
            key = (user, item)
            if key not in pairs or timestamp >= pairs[key].get("unixReviewTime", 0):
                # Do not retain reviewerName: it is unnecessary for the experiment.
                pairs[key] = {k: row[k] for k in (
                    "reviewerID", "asin", "overall", "reviewText", "summary",
                    "unixReviewTime", "reviewTime", "helpful") if k in row}
                pairs[key]["unixReviewTime"] = timestamp
    if not pairs:
        raise ValueError("Dataset contains no interactions")
    records = sorted(pairs.values(), key=lambda r: (r["reviewerID"], r["asin"]))
    user_ids = sorted({r["reviewerID"] for r in records})
    item_ids = sorted({r["asin"] for r in records})
    umap = {v: k for k, v in enumerate(user_ids)}
    imap = {v: k for k, v in enumerate(item_ids)}
    return Dataset(records, user_ids, item_ids,
                   np.array([umap[r["reviewerID"]] for r in records]),
                   np.array([imap[r["asin"]] for r in records]),
                   np.array([float(r["overall"]) for r in records]),
                   digest.hexdigest(), count - len(records))


def user_holdout(users, indices, train_ratio=0.8, seed=42):
    """floor(ratio*n) training rows, at least one per side for n>=2.

    A singleton remains in training. Users are processed in sorted order so the
    split is stable independently of dictionary iteration order.
    """
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio must be between 0 and 1")
    rng = np.random.default_rng(seed)
    train, holdout = [], []
    indices = np.asarray(indices, dtype=np.int64)
    for user in np.unique(users[indices]):
        rows = indices[users[indices] == user].copy()
        rng.shuffle(rows)
        ntrain = max(1, min(len(rows) - 1, math.floor(train_ratio * len(rows))))
        train.extend(rows[:ntrain])
        holdout.extend(rows[ntrain:])
    return np.sort(train).astype(np.int64), np.sort(holdout).astype(np.int64)


def dense_training(data, indices):
    matrix = np.zeros((len(data.user_ids), len(data.item_ids)), dtype=np.float64)
    matrix[data.users[indices], data.items[indices]] = data.ratings[indices]
    return matrix


def write_splits(data, splits, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, indices in splits.items():
        with (directory / f"{name}.jsonl").open("w", encoding="utf-8") as stream:
            for idx in indices:
                stream.write(json.dumps(data.records[int(idx)], ensure_ascii=False) + "\n")
    np.savez_compressed(directory / "indices.npz", **splits)
    (directory / "id_maps.json").write_text(json.dumps({
        "user_ids": data.user_ids, "item_ids": data.item_ids}, indent=2), encoding="utf-8")
