"""One-command experiment: split, validation selection, refit, test, export."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import platform
import time

import numpy as np

from .data import load_dataset, user_holdout, dense_training, write_splits
from .models import make_model, save_model, MODELS
from .metrics import rating_metrics, evaluate_ranking
from .reporting import write_report


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if not rows and fieldnames is None:
        raise ValueError("Empty CSV requires fieldnames")
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_config(config):
    for name in ("train_ratio", "validation_train_ratio"):
        if not 0 < config[name] < 1:
            raise ValueError(f"{name} must be in (0, 1)")
    if config["top_k"] != 10:
        raise ValueError("The course protocol requires top_k=10")
    if not config["models"]:
        raise ValueError("At least one model is required")
    for name, grid in config["models"].items():
        if name not in MODELS or not grid:
            raise ValueError(f"Unknown model or empty grid: {name}")
        for params in grid:
            model = make_model(name, params)
            for key in ("reg", "iterations", "neighbors", "shrinkage", "factors", "factor_reg", "epochs"):
                if hasattr(model, key) and getattr(model, key) <= 0:
                    raise ValueError(f"{name}.{key} must be positive")


def run_experiment(config):
    validate_config(config)
    started = time.perf_counter()
    out = Path(config["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    data = load_dataset(config["data_path"])
    all_rows = np.arange(len(data.records))
    train, test = user_holdout(data.users, all_rows, config["train_ratio"], config["seed"])
    fit, validation = user_holdout(data.users, train, config["validation_train_ratio"], config["seed"] + 1)
    if not len(test) or not len(validation):
        raise ValueError("Dataset is too small for nonempty test and validation splits")
    splits = {"train": train, "test": test, "fit": fit, "validation": validation}
    write_splits(data, splits, out / "splits")
    matrix_fit = dense_training(data, fit)
    matrix_train = dense_training(data, train)
    counts = np.bincount(data.users, minlength=len(data.user_ids))
    item_counts = np.bincount(data.items, minlength=len(data.item_ids))
    stats = {
        "interactions": len(data.records), "users": len(data.user_ids), "items": len(data.item_ids),
        "density": len(data.records) / len(data.user_ids) / len(data.item_ids),
        "min_user_ratings": int(counts.min()), "max_user_ratings": int(counts.max()),
        "min_item_ratings": int(item_counts.min()), "max_item_ratings": int(item_counts.max()),
        "rating_distribution": {str(i): int(np.sum(data.ratings == i)) for i in range(1, 6)},
        "mean_rating": float(data.ratings.mean()), "duplicates_removed": data.duplicates_removed,
        "start_date": datetime.fromtimestamp(min(r["unixReviewTime"] for r in data.records), timezone.utc).date().isoformat(),
        "end_date": datetime.fromtimestamp(max(r["unixReviewTime"] for r in data.records), timezone.utc).date().isoformat(),
        "split_counts": {name: len(rows) for name, rows in splits.items()},
        "actual_train_ratio": len(train) / len(data.records),
        "cold_test_items": int(np.sum(~matrix_train.any(axis=0))),
        "cold_test_rows": int(np.sum(~matrix_train.any(axis=0)[data.items[test]])),
        "catalog_known_at_split": True,
    }
    write_json(out / "data_stats.json", stats)
    print(f"Data: {stats['interactions']} ratings, {stats['users']} users, {stats['items']} items", flush=True)
    print(f"Split: train={len(train)}, test={len(test)}, inner fit={len(fit)}, validation={len(validation)}", flush=True)
    trials, selections = [], {}
    # Select all settings and winners BEFORE touching test labels.
    for name, grid in config["models"].items():
        model_trials = []
        for trial_id, original_params in enumerate(grid):
            params = dict(original_params)
            if name == "MFALS":
                params["seed"] = config["seed"]
            tick = time.perf_counter()
            model = make_model(name, params).fit(matrix_fit)
            rating = {} if name == "Popularity" else rating_metrics(data.ratings[validation],
                model.predict(data.users[validation], data.items[validation]))
            ranking, _, _ = evaluate_ranking(model, data.users[validation], data.items[validation], config["top_k"])
            trial = {"model": name, "trial": trial_id, "params": params,
                     **rating, **ranking, "seconds": time.perf_counter() - tick}
            trials.append(trial)
            model_trials.append(trial)
            print(f"Validation {name} {trial_id+1}/{len(grid)}: "
                  f"RMSE={rating.get('rmse', 'n/a')} NDCG={ranking['ndcg']:.6f}", flush=True)
        # Rating models tune on RMSE, popularity has a single fixed setting.
        best = min(model_trials, key=lambda t: t.get("rmse", -t["ndcg"]))
        selections[name] = best
    rating_choices = [v for v in selections.values() if "rmse" in v]
    best_rating = min(rating_choices, key=lambda t: t["rmse"])["model"] if rating_choices else None
    best_ranking = max(selections.values(), key=lambda t: t["ndcg"])["model"]
    write_json(out / "validation_trials.json", trials)
    selection = {"rating_model": best_rating, "ranking_model": best_ranking,
                 "selection_basis": "inner-validation RMSE for rating, NDCG@10 for ranking; no test selection",
                 "model_settings": {name: t["params"] for name, t in selections.items()}}
    write_json(out / "selection.json", selection)
    results = []
    for name, selected in selections.items():
        tick = time.perf_counter()
        model = make_model(name, selected["params"]).fit(matrix_train)
        train_seconds = time.perf_counter() - tick
        rating = {}
        if name != "Popularity":
            predictions = model.predict(data.users[test], data.items[test])
            rating = rating_metrics(data.ratings[test], predictions)
            write_csv(out / "predictions" / f"{name}.csv", ({
                "reviewerID": data.user_ids[data.users[idx]], "asin": data.item_ids[data.items[idx]],
                "actual": float(data.ratings[idx]), "predicted": float(pred),
                "absolute_error": float(abs(data.ratings[idx] - pred))} for idx, pred in zip(test, predictions)))
        rank, per_user, recs = evaluate_ranking(model, data.users[test], data.items[test], config["top_k"])
        for row in per_user:
            row["reviewerID"] = data.user_ids[row["user_index"]]
        write_csv(out / "per_user" / f"{name}.csv", per_user)
        write_csv(out / "recommendations" / f"{name}.csv", ({
            "reviewerID": data.user_ids[user], "rank": pos, "asin": data.item_ids[int(item)],
            "score": float(score), "score_type": "training_count" if name == "Popularity" else "unclipped_rating"
        } for user, items, scores in recs for pos, (item, score) in enumerate(zip(items, scores), 1)))
        save_model(model, out / "models" / f"{name}.npz", data.user_ids, data.item_ids, selected["params"])
        if hasattr(model, "loss_history"):
            write_json(out / "als_loss_history.json", model.loss_history)
        result = {"model": name, "params": selected["params"], **rating, **rank,
                  "train_seconds": train_seconds, "total_seconds": time.perf_counter() - tick}
        results.append(result)
        print(f"Test {name}: MAE={rating.get('mae', 'n/a')} RMSE={rating.get('rmse', 'n/a')} "
              f"P@10={rank['precision']:.6f} R@10={rank['recall']:.6f} NDCG@10={rank['ndcg']:.6f}", flush=True)
    write_json(out / "metrics.json", results)
    fields = ["model", "mae", "rmse", "precision", "recall", "f_measure", "macro_f1", "ndcg", "catalog_coverage", "train_seconds"]
    write_csv(out / "comparison.csv", ({k: r.get(k, "") for k in fields} for r in results), fields)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "config": config,
                "data_sha256": data.source_sha256, "python": platform.python_version(),
                "numpy": np.__version__, "platform": platform.platform(),
                "elapsed_seconds": time.perf_counter() - started}
    write_json(out / "manifest.json", manifest)
    write_report(out, stats, trials, selection, results, manifest)
    print(f"Selected on validation: rating={best_rating}, ranking={best_ranking}", flush=True)
    print(f"Completed in {manifest['elapsed_seconds']:.1f}s. Results: {out.resolve()}", flush=True)
    return results
