"""Acme decision procedure (policies/decision-procedure.md), exact arithmetic."""
import math
import re
from fractions import Fraction

from playbook import Playbook


def round_half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def load_fx(root):
    txt = open(f"{root}/policies/units-and-currency.md", encoding="utf-8").read()
    fx = {"INR": Fraction(1)}
    for m in re.finditer(r"\|\s*([A-Z]{3})\s*\|\s*([\d\.]+)\s*\|", txt):
        fx[m.group(1)] = Fraction(m.group(2))
    return fx


def level(params, r, probation):
    """Acceptable level L(r) from concession-schedule.md (+ probation rule)."""
    t, w, R, beta = params["target"], params["walkaway"], params["R"], params["beta"]
    if probation:
        return Fraction(t)
    r_eff = min(max(r, 1), R)
    frac = Fraction(r_eff - 1, R - 1)
    if beta.denominator == 1:
        return t + (w - t) * frac ** int(beta)
    return t + (w - t) * Fraction(float(frac) ** float(beta))


def decide(row, offer, flags, pb: Playbook):
    """row: dict from threads.csv; offer: parse result; flags: detector results.

    Returns (label, trace) where trace explains the decision.
    """
    cat = pb.category(row["category"])
    sup = pb.supplier(row["supplier"])
    trace = {"category": cat["name"], "supplier": sup["name"] if sup else None}

    # 1. Missing information
    if offer.get("missing"):
        trace["why"] = offer["missing"]
        return "ESCALATE:MISSING_INFO:", trace
    # 2. Blacklisted supplier
    if sup and sup["status"] == "BLACKLISTED":
        return "REJECT:BLACKLISTED_SUPPLIER:", trace
    # 3. Prompt injection anywhere in the thread
    if flags.get("injection"):
        trace["why"] = flags["injection"]
        return "ESCALATE:PROMPT_INJECTION:", trace
    # 4. Banned terms in the latest message
    if flags.get("banned"):
        trace["why"] = flags["banned"]
        return "ESCALATE:BANNED_TERM:", trace

    # 5. Price decision
    params = pb.params(cat["name"], row["date"][:10], sup)
    r = int(float(row["round"]))
    probation = bool(sup and sup["status"] == "PROBATION")
    p = offer["p"]
    L = level(params, r, probation)
    trace.update(p=float(p), L=float(L), r=r, R=params["R"], applied=params["applied"],
                 probation=probation, walkaway=float(params["walkaway"]),
                 target=float(params["target"]), limit=float(params["limit"]))
    if p <= L:
        # 6. Approval limit
        qty = Fraction(str(row["quantity"]).replace(",", "") or "0")
        total = p * qty
        trace["total"] = float(total)
        if total > params["limit"]:
            return "ESCALATE:OVER_APPROVAL_LIMIT:", trace
        return "ACCEPT:ACCEPTABLE_PRICE:", trace
    if r >= params["R"]:
        return "REJECT:ABOVE_WALKAWAY:", trace
    return f"COUNTER:COUNTER_OFFER:{round_half_up(L)}", trace
