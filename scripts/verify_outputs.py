"""Independently recompute metrics from CSV exports and audit split boundaries."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from gardenrec.data import load_dataset
from gardenrec.metrics import rating_metrics, ranking_for_user


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="outputs/default")
    args = parser.parse_args()
    root = Path(args.results)
    manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    data = load_dataset(manifest["config"]["data_path"])
    assert data.source_sha256 == manifest["data_sha256"], "Raw data SHA256 changed"
    with np.load(root/"splits/indices.npz", allow_pickle=False) as indices:
        train, test, fit, validation = [indices[k] for k in ("train", "test", "fit", "validation")]
    assert not set(train) & set(test)
    assert set(train) | set(test) == set(range(len(data.records)))
    assert set(fit) | set(validation) == set(train)
    assert not set(fit) & set(validation)
    seen = {u: set() for u in data.user_ids}
    relevant = {u: set() for u in data.user_ids}
    for idx in train:
        seen[data.user_ids[data.users[idx]]].add(data.item_ids[data.items[idx]])
    for idx in test:
        relevant[data.user_ids[data.users[idx]]].add(data.item_ids[data.items[idx]])
    for result in json.loads((root/"metrics.json").read_text(encoding="utf-8")):
        name = result["model"]
        recs = {u: [] for u in data.user_ids if relevant[u]}
        with (root/"recommendations"/f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                recs[row["reviewerID"]].append(row["asin"])
        per_user = []
        for user, items in recs.items():
            assert len(items) == min(10, len(data.item_ids) - len(seen[user]))
            assert len(items) == len(set(items)) and not set(items) & seen[user]
            per_user.append(ranking_for_user(items, relevant[user]))
        for key in ("precision", "recall", "ndcg"):
            assert abs(np.mean([m[key] for m in per_user]) - result[key]) < 1e-12
        p, r = result["precision"], result["recall"]
        expected_f = 2*p*r/(p+r) if p+r else 0
        assert abs(expected_f - result["f_measure"]) < 1e-12
        if name != "Popularity":
            with (root/"predictions"/f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            assert len(rows) == len(test)
            check = rating_metrics([float(r["actual"]) for r in rows], [float(r["predicted"]) for r in rows])
            assert all(abs(check[k] - result[k]) < 1e-12 for k in check)
        print(f"{name}: split, unseen recommendations and exported metrics verified")
    print("All output audits passed")


if __name__ == "__main__":
    main()
