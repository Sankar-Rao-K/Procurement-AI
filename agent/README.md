# Procurement Desk agent (Data Sprint 2.0)

Deterministic, rule-based agent. No AI model or API is used: every label is produced by
code that reads Acme's playbook files and applies policies/decision-procedure.md
in order (missing info, blacklist, prompt injection, banned terms, price/concession,
approval limit, probation).

## Run (Python 3.9+, standard library only)
    # check against the 40 worked examples
    python agent/run.py --playbook playbook --threads sample_threads.csv --answers sample_answers.csv
    # make the submission (+ per-thread trace and a pattern audit)
    python agent/run.py --playbook playbook --threads threads.csv --out submission.csv --trace trace.jsonl --audit audit.txt

## Files
- playbook.py: loads categories, suppliers (status, price caps, FX), amendments (applied by effective date)
- engine.py: decision procedure, concession schedule L(r), probation, approval limit (exact fractions, x.5 rounds up)
- parser.py: splits [Earlier]/[Latest] message blocks, finds money mentions, detects prompt injection (any message, several languages) and banned terms (latest message)
- offer.py: normalizes the latest offer: FX (contract rate first), GST-inclusive, month/year, packs/reams/dozens, totals, ranges (high end), tiers, volume discounts, free units, list-price and previous-quote discounts, corrections
- run.py: CLI; writes submission, trace and audit
