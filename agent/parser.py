"""Supplier-message parsing: latest message, offer price, injection, banned terms.

First cut written from the playbook only; tuned against threads.csv.
"""
import re
from fractions import Fraction

from amounts import WORD_NUM_RE, words_to_number, MULT

# ---------------------------------------------------------------- currencies
CUR_SYMBOL = [
    (r"₹|\bRs\.?|\bINR\b|\brupees?\b", "INR"),
    (r"US\$|\bUSD\b|\$|\bdollars?\b", "USD"),
    (r"€|\bEUR\b|\beuros?\b", "EUR"),
    (r"£|\bGBP\b|\bpounds?(?:\s+sterling)?\b|\bsterling\b", "GBP"),
]
UNKNOWN_CUR = (r"¥|\bJPY\b|\byen\b|\bAED\b|\bdirhams?\b|\bSGD\b|S\$|\bAUD\b|A\$|\bCAD\b|C\$|"
               r"\bCHF\b|\bfrancs?\b|\bCNY\b|\byuan\b|\bRMB\b|\bHKD\b|\bNZD\b|\bSAR\b|\briyals?\b|"
               r"\bBDT\b|\bNPR\b|\bLKR\b|\bPKR\b|\bMYR\b|\bringgit\b|\bTHB\b|\bbaht\b|\bKRW\b|\bwon\b|"
               r"\bZAR\b|\brand\b|\bSEK\b|\bNOK\b|\bDKK\b|\bkronor?\b|\bkroner\b|\bRUB\b|\broubles?\b|"
               r"\bBRL\b|\breais\b|\bMXN\b|\bpesos?\b|\bIDR\b|\brupiah\b|\bQAR\b|\bKWD\b|\bdinars?\b|"
               r"\bTRY\b|\blira\b|\bPHP\b|\bVND\b|\bdong\b|\bCNH\b")
CUR_ALT = "|".join(f"(?:{p})" for p, _ in CUR_SYMBOL) + "|" + UNKNOWN_CUR


def cur_code(tok):
    for p, c in CUR_SYMBOL:
        if re.fullmatch(p, tok.strip(), re.I):
            return c
    return "OTHER"


NUM = r"\d[\d,]*(?:\.\d+)?"
MULTW = r"lakhs?|lacs?|crores?|cr|thousand|million|mn|k\b|hundred"
AMT = rf"(?P<num>{NUM})\s*(?P<mult>{MULTW})?"
WORDAMT = r"(?P<words>" + WORD_NUM_RE.pattern.strip(r"\b") + r")"

MONEY_RE = re.compile(
    rf"(?P<cur1>{CUR_ALT})\s*(?:{AMT})"
    rf"|(?:{AMT.replace('num', 'num2').replace('mult', 'mult2')})\s*(?P<cur2>{CUR_ALT})",
    re.I)
MONEY_WORD_RE = re.compile(
    rf"(?P<cur1>{CUR_ALT})\s*{WORDAMT}|{WORDAMT.replace('words', 'words2')}\s+(?P<cur2>{CUR_ALT})",
    re.I)


def find_money(text):
    """All money mentions: list of dict(start, end, value, cur)."""
    out = []
    for m in MONEY_RE.finditer(text):
        num = m.group("num") or m.group("num2")
        mult = m.group("mult") or m.group("mult2")
        cur = m.group("cur1") or m.group("cur2")
        if not num or not re.search(r"\d", num):
            continue
        numc = num.rstrip(",.")
        v = Fraction(numc.replace(",", ""))
        if mult:
            v *= MULT[mult.lower()]
        out.append({"start": m.start(), "end": m.end(), "value": v, "cur": cur_code(cur),
                    "raw": m.group(0)})
    taken = [(o["start"], o["end"]) for o in out]
    for m in MONEY_WORD_RE.finditer(text):
        if any(s <= m.start() < e or s < m.end() <= e for s, e in taken):
            continue
        w = m.group("words") or m.group("words2")
        v = words_to_number(w)
        if v is None:
            continue
        cur = m.group("cur1") or m.group("cur2")
        out.append({"start": m.start(), "end": m.end(), "value": v, "cur": cur_code(cur),
                    "raw": m.group(0)})
    out.sort(key=lambda o: o["start"])
    return out


# ------------------------------------------------------------ thread splitting
SPLIT_RE = re.compile(
    r"(?im)^\s*(?:-{2,}\s*(?:original|previous|earlier|forwarded)[^\n]*-*|"
    r"on .{3,80} wrote:|>+.*|from:.*|\[(?:earlier|previous)[^\]]*\]|"
    r"(?:earlier|previous) (?:message|email|reply)s?:?)\s*$")


HEADER_RE = re.compile(r"^\s*\[(Earlier|Latest) message\s*[—–-]+\s*([^,\]]+?)\s*(?:,\s*([^\]]*))?\]\s*$",
                       re.I | re.M)


def thread_blocks(text):
    """Split a thread into [{kind, sender, date, body}] in chronological order."""
    text = (text or "").replace("\r\n", "\n")
    hs = list(HEADER_RE.finditer(text))
    if not hs:
        return [{"kind": "latest", "sender": None, "date": None, "body": text}]
    out = []
    if text[:hs[0].start()].strip():
        out.append({"kind": "earlier", "sender": None, "date": None, "body": text[:hs[0].start()]})
    for i, h in enumerate(hs):
        end = hs[i + 1].start() if i + 1 < len(hs) else len(text)
        out.append({"kind": h.group(1).lower(), "sender": h.group(2).strip(),
                    "date": h.group(3), "body": text[h.end():end]})
    return out


def split_thread(text):
    """Return (latest_body, earlier_supplier_bodies [oldest..newest])."""
    blocks = thread_blocks(text)
    latest_i = max((i for i, b in enumerate(blocks) if b["kind"] == "latest"), default=len(blocks) - 1)
    latest = blocks[latest_i]["body"]
    earlier = [b["body"] for b in blocks[:latest_i]
               if not (b["sender"] or "").lower().startswith("acme")]
    return latest, earlier


# ------------------------------------------------------------ prompt injection
INJ_PATTERNS = [
    r"\b(?:ai|a\.i\.)\b(?![\s-]*(?:powered|driven|enabled|based))",
    r"\blanguage model\b", r"\bllm\b", r"\bgpt\b", r"\bchat ?bot\b", r"\bbot\b",
    r"\bautomated (?:system|agent|reviewer|assistant|procurement|process)",
    r"\b(?:ai|virtual|digital|automated) assistant\b",
    r"\bdear (?:assistant|agent|model|system|reviewer)\b", r"\breviewers?\b",
    r"\b(?:the |any )?(?:automated |procurement |ai )?(?:agent|reviewer|model|system)\s*(?:reading|processing|reviewing|handling|evaluating|parsing)\b",
    r"\boverride\b", r"\bignore (?:all |any |the |your )?(?:previous|prior|above|earlier|other)?\s*(?:instructions|rules|policies|guidelines|playbook)",
    r"\bdisregard (?:all |any |the |your )?(?:previous|prior|above|earlier)?\s*(?:instructions|rules|policies|guidelines|playbook)",
    r"\b(?:already|pre-?)\s*(?:been\s+)?(?:approved|authori[sz]ed|cleared|signed off)",
    r"\bapproval (?:has|was) (?:already )?been granted\b", r"\bapproval (?:is )?already granted\b",
    r"\bsystem (?:prompt|message|instruction|note)\b", r"^\s*system\s*:",
    r"\b(?:instructions? (?:to|for) (?:the )?(?:ai|bot|model|agent|system|reviewer))",
    r"\bnote (?:to|for) (?:the )?(?:ai|bot|model|agent|system|reviewer|language model|assistant)",
    r"\b(?:respond|reply|output|classify|label|mark) (?:this|the deal|the offer)? ?(?:with|as) ['\"]?(?:accept|approved)",
    r"\badmin(?:istrator)? (?:mode|override|instruction)",
    # other languages
    r"ignora (?:las|todas las|tus|sus) (?:instrucciones|reglas)", r"ignorez (?:les|toutes les|vos) (?:instructions|règles)",
    r"ignoriere (?:alle|die|deine) (?:vorherigen |bisherigen )?(?:anweisungen|regeln)", r"déjà (?:été )?approuvé",
    r"ya (?:ha sido |fue |está )?aprobad", r"bereits genehmigt", r"já (?:foi )?aprovad",
    r"\binteligencia artificial\b", r"\bintelligence artificielle\b", r"\bkünstliche intelligenz\b",
    r"\binteligência artificial\b", r"\bintelligenza artificiale\b",
    r"\bsistema automatizado\b", r"\bsystème automatisé\b", r"\bautomatisiertes? system\b", r"\bsistema automatico\b",
    r"\b(?:modelo|modèle|modell|modello) (?:de )?(?:lenguaje|langage|linguistico|sprachmodell)",
    r"\bsprachmodell\b", r"\bassistente? (?:virtual|virtuel)\b",
    r"\b(?:aprueba|aprobar|approuvez|approuver|genehmigen|genehmige|aprove|aprovar|approva|approvare)\b",
    r"\b(?:revisor|réviseur|prüfer|revisore)\b",
    r"एआई|कृत्रिम बुद्धि|स्वचालित|भाषा मॉडल|निर्देशों|अनदेखा|स्वीकृत|मंजूर|अनुमोदित|बॉट",
    r"人工知能|自動|承認|忽略|批准|人工智能|系统|指令",
    r"\bAI ko\b|\bbot ko\b|\bapprove kar\w*",
]
# case-sensitive acronyms: German KI, Spanish/French/Portuguese/Italian IA
INJ_CASE_SENSITIVE = [r"\bKI\b", r"\bKI-\w+", r"\bIA\b", r"\bl'IA\b"]
INJ_WHITELIST = [r"ai[\s-]*powered", r"system integration team", r"\berp system\b",
                 r"\bassistant (?:manager|director|vice president|vp|accountant|engineer)\b",
                 r"\b(?:executive|sales|admin(?:istrative)?|personal|accounts?|procurement|marketing|office) assistant\b"]


def detect_injection(text):
    t = text
    for w in INJ_WHITELIST:
        t = re.sub(w, " ", t, flags=re.I)
    for p in INJ_PATTERNS:
        m = re.search(p, t, re.I | re.M)
        if m:
            return m.group(0)
    for p in INJ_CASE_SENSITIVE:
        m = re.search(p, t, re.M)
        if m:
            return m.group(0)
    return None


# ---------------------------------------------------------------- banned terms
NUMWORD_PCT = {"half": 50, "one third": 33.4, "a third": 33.4, "two thirds": 66.7,
               "two-thirds": 66.7, "one-third": 33.4, "a quarter": 25, "one quarter": 25,
               "three quarters": 75, "full": 100, "entire": 100, "whole": 100, "all": 100}


def _pct_value(s):
    s = s.strip().lower()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(?:%|per ?cent|pc)", s)
    if m:
        return float(m.group(1))
    m = re.match(r"(.+?)\s*(?:per ?cent|%)", s)
    if m:
        v = words_to_number(m.group(1))
        if v is not None:
            return float(v)
    for k, v in NUMWORD_PCT.items():
        if s.startswith(k):
            return v
    return None


PCT = r"(?:\d+(?:\.\d+)?\s*(?:%|per ?cent)|[a-z\- ]+?\s+per ?cent|half|one[- ]third|a third|two[- ]thirds|a quarter|one quarter|three quarters|full|entire|whole|100%)"


def detect_banned(text):
    t = text.lower()
    # automatic renewal
    neg_ren = re.search(r"(?:no|not|never|without|won't|will not|does not|doesn't)\s+(?:\w+\s+){0,3}(?:auto(?:matic(?:ally)?)?[\s-]*renew)", t)
    ren = re.search(r"auto[\s-]*renew|automatic(?:ally)? renew|renews? automatically|renews? on its own|"
                    r"(?:year|month)[\s-]+(?:to|on|after)[\s-]+(?:year|month)\s+unless|"
                    r"continues?\s+(?:\w+\s+){0,6}unless\s+(?:\w+\s+){0,4}(?:cancel|terminat|notice)|"
                    r"rolls? over|evergreen|renewed automatically|automatically extend|auto[\s-]*extend",
                    t)
    if ren and not neg_ren:
        return "auto-renewal: " + ren.group(0)
    # upfront / advance payment above 30%
    for m in re.finditer(rf"(?P<pct>{PCT})\s*(?:of the (?:order|total|contract)(?: value)?\s*)?(?:payment\s*)?(?:paid\s*|payable\s*|due\s*|to be paid\s*)?(?:up[\s-]*front|in advance|as (?:an )?advance|advance)", t):
        v = _pct_value(m.group("pct"))
        if v is not None and v > 30:
            return "advance: " + m.group(0)
    for m in re.finditer(rf"(?:up[\s-]*front|advance)(?: payment)?(?: of)?\s*(?P<pct>{PCT})", t):
        v = _pct_value(m.group("pct"))
        if v is not None and v > 30:
            return "advance: " + m.group(0)
    if re.search(r"(?:full|entire|whole|100%) (?:payment|amount|value)\s*(?:\w+\s+){0,3}(?:up[\s-]*front|in advance)", t):
        return "advance: full"
    # unlimited liability
    if re.search(r"unlimited liability|liability (?:is |shall be |will be )?(?:unlimited|uncapped)|uncapped liability|"
                 r"no (?:cap|limit) on (?:acme'?s? |your )?liability", t) and not re.search(
                 r"(?:no|not|never|without)\s+(?:\w+\s+){0,3}unlimited liability", t):
        return "unlimited liability"
    # exclusivity
    excl = re.search(r"exclusiv|sole supplier|only from us|exclusively|solely from us|single[- ]source", t)
    neg_excl = re.search(r"(?:no|not|never|without|non)[\s-]+(?:\w+\s+){0,4}exclusiv|non-exclusive|exclusivity is not", t)
    if excl and not neg_excl:
        return "exclusivity: " + excl.group(0)
    return None
