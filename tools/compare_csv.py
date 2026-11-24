"""Compare two submission files label by label.

Usage:
  python tools/compare_csv.py reproduced_submission.csv submission/submission.csv

Exit code 0 when every thread_id has the same label in both files.
"""
import csv
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return {r["thread_id"]: r["label"] for r in csv.DictReader(f)}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    a, b = load(sys.argv[1]), load(sys.argv[2])
    ids = sorted(set(a) | set(b))
    diffs = [(t, a.get(t), b.get(t)) for t in ids if a.get(t) != b.get(t)]
    print(f"{len(ids) - len(diffs)} / {len(ids)} thread labels identical")
    for t, x, y in diffs[:20]:
        print(f"  {t}: {sys.argv[1]} = {x}   |   {sys.argv[2]} = {y}")
    if len(diffs) > 20:
        print(f"  ... and {len(diffs) - 20} more")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
