"""Build a reviewable course submission without datasets or user-level artifacts."""
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    paths = [root / name for name in ("README.md", "requirements.txt", "requirements-authoring.txt", "pyproject.toml", ".gitignore")]
    for directory in ("gardenrec", "configs", "tests", "scripts", "docs", "deliverables"):
        paths.extend(p for p in (root / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc",))
    paths.append(root / "data" / "README.md")
    for name in ("metrics.json", "comparison.csv", "data_stats.json", "selection.json", "manifest.json", "validation_trials.json"):
        path = root / "outputs" / "default" / name
        if path.exists():
            paths.append(path)
    destination = root / "dist" / "gardenrec_submission.zip"
    destination.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            if path.exists():
                archive.write(path, path.relative_to(root).as_posix())
    print(f"Created {destination} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
