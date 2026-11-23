"""Normalize the supplier's current offer to p (INR excl. GST per normalized unit)."""
import re
from fractions import Fraction

from amounts import words_to_number
from parser import find_money

PERIOD_MONTH = (r"(?:per|a|/|each|every)\s*(?:calendar\s+)?(?:month|mo)\b|\bmonthly\b|"
                r"\bp\.?\s?m\.?(?=[\s,.;)]|$)|/\s*mo(?:nth)?\b|\bmonth(?:ly)? (?:fee|charge|rate|basis)")
PERIOD_YEAR = (r"(?:per|a|/|each|every)\s*(?:calendar\s+)?(?:year|yr|annum)\b|\bannual(?:ly)?\b|"
               r"\byearly\b|\bp\.?\s?a\.?(?=[\s,.;)]|$)|/\s*y(?:ea)?r\b|\byear(?:ly)? (?:fee|charge|rate|basis)")
GST_INCL = (r"(?:incl(?:\.|usive|uding|udes)?|inc\.?|with)\s*(?:of\s*)?(?:all\s*)?(?:the\s*)?(?:\d+\s*%\s*)?(?:gst|taxes)|"
            r"gst[\s-]*(?:incl(?:\.|usive|uded)?|inc\.?)\b|gst included|inclusive of (?:all )?tax|"
            r"(?:includes|including|include) (?:\d+\s*%\s*)?gst|gst is included")
GST_EXCL = (r"(?:excl(?:\.|usive|uding|udes)?|ex\.?|before|plus|\+|without|not including)\s*(?:of\s*)?(?:\d+\s*%\s*)?gst|"
            r"gst (?:extra|excluded|additional|not included|will be (?:charged|added|extra))|pre-?gst|"
            r"(?:excludes|exclude) gst")
CORRECTION = (r"correction|typo|should (?:have )?(?:read|been|say)|i meant|we meant|"
              r"mis-?typed|error in (?:my|our|the)|revised figure|please read (?:it|the price) as")

COUNT_WORD = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)"
PREV_QUOTE = (r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)\s+(?:off|discount on|discount off|below|lower than|"
              r"reduction on|less than)\s+(?:our\s+|my\s+|the\s+)?(?:previous|earlier|last|original|prior|"
              r"initial|first)\s+(?:quote|quotation|price|offer|bid)")


def _cnt(s):
    return int(s) if s.isdigit() else int(words_to_number(s))


def _int(s):
    return int(s.replace(",", ""))


def _sentence(text, start, end):
    """The sentence (line-bounded) containing [start, end)."""
    bounds = [0] + [m.end() for m in SENT_BOUND.finditer(text)] + [len(text)]
    a = max(b for b in bounds if b <= start)
    b = min([b for b in bounds if b >= end] or [len(text)])
    return text[a:b]


SENT_BOUND = re.compile(r"\n|(?<!\bRs)(?<!\brs)(?<!\bRS)(?<!\bincl)(?<!\bIncl)(?<!\bINCL)(?<!\bexcl)(?<!\bExcl)(?<!\bEXCL)(?<!\bapprox)(?<!\bApprox)(?<!\bNo)(?<!\bno)(?<!\bex)(?<!\bEx)(?<!\binc)(?<!\bInc)(?<!\bp\.a)(?<!\bp\.m)(?<!\bvs)(?<!\bLtd)(?<!\bPvt)(?<!\bCo)(?<!\bapprox)\.\s+(?=[A-Z\[(])")


def normalize(value, cur, after, sentence, full, cat, params):
    """Currency, units/packs, billing period and GST for one quoted amount.

    after: text right after the amount; sentence: the amount's sentence;
    full: the whole message (lower-case).
    """
    notes = []
    if cur == "OTHER":
        return None, "unlisted currency"
    rate = params["fx_override"].get(cur, params["fx_table"].get(cur))
    if rate is None:
        return None, "unlisted currency"
    v = value * rate
    if cur != "INR":
        notes.append(f"fx {cur}@{float(rate)}")
    a = after.lower()
    # units / packs
    um = re.match(r"\s*(?:\([^)]*\)\s*)?(?:(?:incl|excl|plus|\+|inclusive|exclusive)[^,;]*?\s+)?"
                  r"(?:per|a|/|each|for each|for every|for one|for a|for each|for 1)\s+(?:single\s+)?([a-z]+)", a)
    word = um.group(1) if um else ""
    if word == "dozen":
        v /= 12
        notes.append("/12 dozen")
    elif word in ("pack", "packs") and cat["pack"] and cat["unit_word"] == "fixture":
        n = int(re.search(r"(\d+)", cat["pack"]).group(1))
        v /= n
        notes.append(f"/{n} pack")
    elif word in ("ream", "reams") and cat["unit_word"] == "box":
        n = int(re.search(r"(\d+)\s*reams", cat["pack"]).group(1)) if cat["pack"] else 10
        v *= n
        notes.append(f"x{n} ream->box")
    # billing period (subscriptions)
    if cat["period"]:
        seg = a[:60]
        mm, my = re.search(PERIOD_MONTH, seg), re.search(PERIOD_YEAR, seg)
        if not (mm or my):
            s = sentence.lower()
            mm, my = re.search(PERIOD_MONTH, s), re.search(PERIOD_YEAR, s)
        if mm and (not my or mm.start() < my.start()):
            per = "month"
        elif my:
            per = "year"
        else:
            return None, "no billing period"
        if per != cat["period"]:
            v = v * 12 if per == "month" else v / 12
            notes.append(f"{per}->{cat['period']}")
    # GST
    s = sentence.lower()
    if re.search(GST_INCL, s) and not re.search(GST_EXCL, s):
        v = v / (1 + params["gst"])
        notes.append("gst-incl")
    elif re.search(GST_INCL, full) and not re.search(GST_EXCL, full):
        v = v / (1 + params["gst"])
        notes.append("gst-incl(msg)")
    return v, notes


TIER_COND = [
    (r"(?:up\s*to|upto|not more than|at most|maximum of|max(?:imum)?\.?)\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:\w+\s+)?or (?:fewer|less)", "le"),
    (r"(?:below|under|fewer than|less than)\s*(\d[\d,]*)", "lt"),
    (r"(\d[\d,]*)\s*(?:\w+\s+)?(?:or more|and above|or above|and over|\+|plus)|(?:at least|minimum(?: of)?|min\.?)\s*(\d[\d,]*)", "ge"),
    (r"(?:above|over|more than|exceeding|beyond|in excess of)\s*(\d[\d,]*)", "gt"),
    (r"(\d[\d,]*)\s*(?:-|–|to)\s*(\d[\d,]*)", "range"),
    (r"larger (?:orders|quantities|volumes)|bigger orders|anything (?:above|more|beyond)|higher (?:quantities|volumes)|beyond that", "larger"),
    (r"smaller (?:orders|quantities|volumes)|anything (?:below|less)", "smaller"),
]


def _tier_condition(seg):
    seg = seg.lower()
    best = None
    for pat, kind in TIER_COND:
        m = re.search(pat, seg)
        if m and (best is None or m.start() < best[2]):
            nums = [_int(g) for g in m.groups() if g] if m.groups() else []
            best = (kind, nums, m.start())
    return best


def _tier_pick(text, cand, qty):
    """Pick the tier matching qty, or None if this isn't a tiered quote."""
    if len(cand) < 2:
        return None
    conds = []
    for i, x in enumerate(cand):
        nxt = cand[i + 1]["start"] if i + 1 < len(cand) else len(text)
        seg = text[x["end"]:min(nxt, x["end"] + 120)]
        seg = re.split(r"\n|\. ", seg)[0]
        conds.append(_tier_condition(seg))
    if sum(c is not None for c in conds) < 2:
        return None
    for x, c in zip(cand, conds):
        if c is None:
            continue
        kind, nums, _ = c
        if kind == "larger":
            others = [n for k, ns, _ in (cc for cc in conds if cc) if k in ("le", "lt") for n in ns]
            ok = bool(others) and all((qty > n) if k == "le" else (qty >= n)
                                      for k, ns, _ in (cc for cc in conds if cc) if k in ("le", "lt") for n in ns)
        elif kind == "smaller":
            others = [(k, n) for k, ns, _ in (cc for cc in conds if cc) if k in ("ge", "gt") for n in ns]
            ok = bool(others) and all((qty < n) if k == "ge" else (qty <= n) for k, n in others)
        elif kind == "le":
            ok = qty <= nums[0]
        elif kind == "lt":
            ok = qty < nums[0]
        elif kind == "ge":
            ok = qty >= nums[0]
        elif kind == "gt":
            ok = qty > nums[0]
        elif kind == "range":
            ok = nums[0] <= qty <= nums[1]
        else:
            ok = False
        if ok:
            return x, c
    return None


def _norm_at(text, x, cat, params):
    after = text[x["end"]:x["end"] + 100]
    return normalize(x["value"], x["cur"], after, _sentence(text, x["start"], x["end"]),
                     text.lower(), cat, params)


def extract(row, latest, earlier, cat, params, depth=0):
    """earlier: list of the supplier's earlier message bodies (oldest..newest)."""
    text = latest
    low = text.lower()
    money = find_money(text)
    qty = int(Fraction(str(row["quantity"]).replace(",", "") or "0"))

    # "D% off our previous quote" -> the supplier's own previous quote
    m = re.search(PREV_QUOTE, low)
    if m and earlier and not [x for x in money if x["start"] < m.start() and
                              m.start() - x["end"] < 40]:
        prev = extract(row, earlier[-1], earlier[:-1], cat, params, depth + 1)
        if prev.get("p") is None:
            return prev
        d = Fraction(m.group(1)) / 100
        return {"p": prev["p"] * (1 - d), "how": f"-{m.group(1)}% of prev [{prev['how']}]"}

    if not money:
        # accepts our last counter?
        if re.search(r"(?:accept|agree to|happy with|go with|take|match|meet)\s+(?:\w+\s+){0,3}"
                     r"(?:your|acme'?s?)\s+(?:last |previous |latest )?(?:counter|offer|price|proposal)", low) \
                and row.get("our_last_counter"):
            return {"p": Fraction(str(row["our_last_counter"]).replace(",", "")), "how": "accepts our counter"}
        return {"missing": "no price"}

    cand = money
    # corrections: the first amount after the last correction marker
    cms = list(re.finditer(CORRECTION, low))
    if cms:
        after = [x for x in money if x["start"] > cms[-1].start()]
        if after:
            cand = after[:1]
            v, notes = _norm_at(text, cand[0], cat, params)
            if v is None:
                return {"missing": notes}
            return {"p": v, "how": f"correction {cand[0]['raw']} {notes}"}

    # D% off list price of X
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)\s+(?:off|discount on|discount off|below)\s+(?:our\s+|the\s+)?"
                  r"(?:standard\s+|regular\s+|published\s+|usual\s+)?list\s+price", low)
    if m:
        after = [x for x in cand if x["start"] >= m.end() - 2]
        if after:
            base = after[0]
            v, notes = _norm_at(text, base, cat, params)
            if v is None:
                return {"missing": notes}
            d = Fraction(m.group(1)) / 100
            return {"p": v * (1 - d), "how": f"list {base['raw']} -{m.group(1)}% {notes}"}

    # ranges -> upper end (P-01, P-04)
    for i in range(len(cand) - 1):
        a, b = cand[i], cand[i + 1]
        between = text[a["end"]:b["start"]].lower()
        before = text[max(0, a["start"] - 20):a["start"]].lower()
        if re.fullmatch(r"\s*(?:and|to|-|–|—)\s*", between) and (
                re.search(r"between|from|range|ranging", before) or re.fullmatch(r"\s*(?:-|–|—|to)\s*", between)):
            hi = max(a, b, key=lambda x: x["value"] * (params["fx_table"].get(x["cur"], 1)))
            v, notes = _norm_at(text, b if hi is b else a, cat, params)
            if hi is a:  # unit words follow the second amount
                v2, notes = normalize(a["value"], a["cur"], text[b["end"]:b["end"] + 100],
                                      _sentence(text, a["start"], b["end"]), low, cat, params)
                v = v2
            if v is None:
                return {"missing": notes}
            return {"p": v, "how": f"range hi {hi['raw']} {notes}"}

    # tiers
    tp = _tier_pick(text, cand, qty)
    if tp:
        x, c = tp
        v, notes = _norm_at(text, x, cat, params)
        if v is None:
            return {"missing": notes}
        return {"p": v, "how": f"tier {c[0]}{c[1]} {x['raw']} {notes}"}

    base = cand[0]
    v, notes = _norm_at(text, base, cat, params)
    if v is None:
        return {"missing": notes}
    how = [base["raw"], notes]
    after = text[base["end"]:base["end"] + 100].lower()

    # totals: "₹X in total for all N units"
    tm = re.match(r"\s*(?:\([^)]*\)\s*)?(?:in total|total|altogether|all[- ]in|for the (?:whole|entire|full) (?:order|lot|quantity))", after)
    pre = text[max(0, base["start"] - 40):base["start"]].lower()
    if tm or re.search(r"(?:total|grand total|overall|lump[- ]sum)\s*(?:of|price|cost|amount|value|is|:)?\s*(?:of\s*)?(?:is\s*)?$", pre):
        mm = re.search(r"for (?:all |the |each of the )?(?:of )?(?:the )?(\d[\d,]*)", after)
        n = _int(mm.group(1)) if mm else qty
        if n:
            v = v / n
            how.append(f"/{n} total")

    # free units: "plus K free for every N you pay for" (P-02, P-05)
    fm = re.search(rf"{COUNT_WORD}\s+(?:\w+\s+)?free\s+(?:\w+\s+)?(?:for|with)\s+every\s+{COUNT_WORD}", low)
    if fm:
        k, n = _cnt(fm.group(1)), _cnt(fm.group(2))
        v = v * n / (n + k)
        how.append(f"free {k}/{n}")

    # volume discount: "an extra D% off for orders of N or more"
    vm = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent)\s+(?:volume\s+|additional\s+|extra\s+|further\s+|bulk\s+)?"
                   r"(?:discount|off|reduction)\b([^.\n]{0,80})", low)
    if vm and not re.search(r"list price|previous|earlier|original", vm.group(0)):
        c = _tier_condition(vm.group(2))
        if c and c[0] in ("ge", "gt", "le", "lt", "range"):
            kind, nums, _ = c
            ok = {"ge": qty >= nums[0], "gt": qty > nums[0], "le": qty <= nums[0],
                  "lt": qty < nums[0], "range": len(nums) > 1 and nums[0] <= qty <= nums[1]}[kind]
            if ok:
                v = v * (1 - Fraction(vm.group(1)) / 100)
            how.append(f"vol -{vm.group(1)}% {kind}{nums} {'applied' if ok else 'not met'}")
    return {"p": v, "how": " ".join(map(str, how))}
