"""Procurement Desk agent.

Usage:
  python run.py --playbook PLAYBOOK_DIR --threads threads.csv --out submission.csv
  python run.py --playbook PLAYBOOK_DIR --threads sample_threads.csv --answers sample_answers.csv
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playbook import Playbook          # noqa: E402
from engine import decide, load_fx     # noqa: E402
from parser import split_thread, detect_injection, detect_banned  # noqa: E402
from offer import extract              # noqa: E402


def label_row(row, pb, fx):
    msg = row["supplier_message"] or ""
    latest, earlier = split_thread(msg)
    cat = pb.category(row["category"])
    sup = pb.supplier(row["supplier"])
    params = pb.params(cat["name"], row["date"][:10], sup)
    params["fx_table"] = fx
    offer = extract(row, latest, earlier, cat, params)
    flags = {"injection": detect_injection(msg), "banned": detect_banned(latest)}
    label, trace = decide(row, offer, flags, pb)
    trace["how"] = offer.get("how")
    trace["latest"] = latest[:300]
    return label, trace


def _mask(s, names):
    import re
    for n in names:
        s = s.replace(n, "<SUP>")
    s = re.sub(r"(₹|Rs\.?|INR|USD|EUR|GBP|\$|€|£)\s*\d[\d,]*(?:\.\d+)?", r"\1<AMT>", s)
    s = re.sub(r"\d[\d,]*(?:\.\d+)?", "<N>", s)
    s = re.sub(r"\b(?:meals?|headsets?|monitors?|participants?|seats?|sites?|guards?|servers?|laptops?|"
               r"chairs?|phones?|fixtures?|boxe?s?|shipments?)\b", "<U>", s)
    s = re.sub(r"^(?:Hi|Hello|Dear|Good morning|Good afternoon)\b.*,$", "<GREETING>", s)
    s = re.sub(r"^(?:Regards|Best|Cheers|Thanks|Warm regards|Thanks and regards|Kind regards|Best regards|Sincerely)\W*$",
               "<SIGNOFF>", s)
    return s.strip()


def write_audit(path, rows, results):
    from collections import Counter, defaultdict
    names = sorted({r["supplier"] for r in rows}, key=len, reverse=True)
    labels = Counter(lbl.split(":")[0] + ":" + lbl.split(":")[1] for _, lbl, _ in results)
    tmpl = defaultdict(list)
    for row, (tid, lbl, tr) in zip(rows, results):
        latest, earlier = split_thread(row["supplier_message"])
        for line in latest.split("\n"):
            line = line.strip()
            if line:
                tmpl[_mask(line, names)].append(tid)
        for e in earlier:
            for line in e.split("\n"):
                if line.strip():
                    tmpl["[EARLIER] " + _mask(line.strip(), names)].append(tid)
    with open(path, "w", encoding="utf-8") as f:
        f.write("LABELS\n")
        for k, v in labels.most_common():
            f.write(f"{v:5d}  {k}\n")
        f.write("\nCATEGORY VALUES: " + ", ".join(sorted({r['category'] for r in rows})) + "\n")
        f.write("SUPPLIER VALUES: " + ", ".join(sorted({r['supplier'] for r in rows})) + "\n")
        f.write("ROUNDS: " + ", ".join(sorted({r['round'] for r in rows})) + "\n")
        f.write("DATES: " + min(r['date'] for r in rows) + " .. " + max(r['date'] for r in rows) + "\n")
        f.write("\nLINE PATTERNS (count, example thread, pattern)\n")
        for k, v in sorted(tmpl.items(), key=lambda kv: -len(kv[1])):
            f.write(f"{len(v):5d}  {v[0]}  {k}\n")
        f.write("\nPER-THREAD DECISIONS\n")
        for tid, lbl, tr in results:
            f.write(f"{tid} {lbl} | {tr.get('how')} | p={tr.get('p')} L={tr.get('L')} | {tr.get('why') or ''} {tr.get('error') or ''}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playbook", required=True)
    ap.add_argument("--threads", required=True)
    ap.add_argument("--answers")
    ap.add_argument("--out")
    ap.add_argument("--trace")
    ap.add_argument("--audit", help="write a compact report of message patterns for review")
    a = ap.parse_args()

    pb = Playbook(a.playbook)
    fx = load_fx(a.playbook)
    rows = list(csv.DictReader(open(a.threads, encoding="utf-8")))
    results = []
    for row in rows:
        try:
            label, trace = label_row(row, pb, fx)
        except Exception as e:  # never crash the whole run
            label, trace = "ESCALATE:MISSING_INFO:", {"error": repr(e)}
        results.append((row["thread_id"], label, trace))

    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["thread_id", "label"])
            for tid, label, _ in results:
                w.writerow([tid, label])
    if a.trace:
        with open(a.trace, "w", encoding="utf-8") as f:
            for (tid, label, trace), row in zip(results, rows):
                f.write(json.dumps({"thread_id": tid, "label": label, **trace,
                                    "row": {k: v for k, v in row.items() if k != "supplier_message"}},
                                   ensure_ascii=False, default=str) + "\n")
    if a.audit:
        write_audit(a.audit, rows, results)
    if a.answers:
        gold = {r["thread_id"]: r["label"] for r in csv.DictReader(open(a.answers, encoding="utf-8"))}
        ok = 0
        for (tid, label, trace), row in zip(results, rows):
            g = gold.get(tid)
            if g == label:
                ok += 1
            else:
                print(f"--- {tid} pred={label} gold={g}")
                print("   ", {k: row[k] for k in row if k != "supplier_message"})
                print("    MSG:", row["supplier_message"][:600].replace("\n", " | "))
                print("    TRACE:", {k: v for k, v in trace.items() if k != "latest"})
        print(f"\nAccuracy: {ok}/{len(gold)} = {ok / len(gold):.3f}")


if __name__ == "__main__":
    main()
