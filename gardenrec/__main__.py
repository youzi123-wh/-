"""CLI entry point, intentionally requiring only NumPy for experiments."""
import os
# Small linear systems run faster and more reproducibly without BLAS oversubscription.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import json
from pathlib import Path
import sys

from .experiment import run_experiment
from .models import load_model


def main(argv=None):
    parser = argparse.ArgumentParser(description="Amazon 园艺商品推荐实验")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="划分、调参、训练、评估并生成报告")
    run.add_argument("--config", default="configs/default.json")
    run.add_argument("--output", help="覆盖配置中的结果目录")
    run.add_argument("--seed", type=int, help="覆盖随机种子")
    rec = sub.add_parser("recommend", help="加载模型，查看某用户未评分商品")
    rec.add_argument("--model", required=True)
    rec.add_argument("--user", required=True, help="原始 reviewerID")
    rec.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
            if args.output:
                config["output_dir"] = args.output
            if args.seed is not None:
                config["seed"] = args.seed
            run_experiment(config)
        else:
            model, metadata = load_model(args.model)
            if args.user not in metadata["user_ids"]:
                raise ValueError("Unknown user. Select a reviewerID from splits/id_maps.json")
            user = metadata["user_ids"].index(args.user)
            items, scores = model.recommend(user, args.top_k)
            print("rank\tasin\tscore")
            for rank, (item, score) in enumerate(zip(items, scores), 1):
                print(f"{rank}\t{metadata['item_ids'][int(item)]}\t{score:.6f}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
