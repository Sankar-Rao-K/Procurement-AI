"""Load Acme's procurement playbook (markdown) into Python structures.

Everything is read from the playbook files themselves, so a playbook change
(new amendment, new supplier contract) is picked up without code edits.
"""
import os
import re
from fractions import Fraction


def _num(s):
    """'₹1,19,990' -> Fraction(119990); '5%' -> Fraction(5)."""
    s = s.replace("₹", "").replace(",", "").replace("%", "").strip()
    return Fraction(s)


def _norm(name):
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


class Playbook:
    def __init__(self, root):
        self.root = root
        self.categories = {}      # canonical name -> dict
        self.cat_alias = {}       # normalized alias -> canonical name
        self.suppliers = {}       # canonical name -> dict
        self.sup_alias = {}
        self.amendments = []      # list of dicts
        self._load_categories()
        self._load_suppliers()
        self._load_amendments()

    # ------------------------------------------------------------ categories
    def _load_categories(self):
        d = os.path.join(self.root, "categories")
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            txt = open(os.path.join(d, fn), encoding="utf-8").read()
            name = re.search(r"#\s*Category:\s*(.+)", txt).group(1).strip()

            def field(label):
                m = re.search(r"\*\*" + re.escape(label) + r":\*\*\s*(.+)", txt)
                return m.group(1).strip() if m else None

            unit = field("Normalized unit")
            cat = {
                "name": name,
                "slug": fn[:-3],
                "unit": unit,
                "gst": _num(field("GST rate")) / 100,
                "target": _num(field("Target price")),
                "walkaway": _num(field("Walk-away price")),
                "R": int(field("Negotiation rounds (R)")),
                "beta": _num(field("Concession exponent (β)")),
                "limit": _num(field("Approval limit")),
                "pack": field("Pack conversion"),
                "period": None,
            }
            u = unit.lower()
            if "per year" in u:
                cat["period"] = "year"
            elif "per month" in u:
                cat["period"] = "month"
            # base unit word, e.g. 'meal', 'site', 'seat', 'box', 'fixture'
            m = re.search(r"per (\w+)", u)
            cat["unit_word"] = m.group(1) if m else None
            self.categories[name] = cat
            for alias in {name, fn[:-3], name.replace(" services", ""),
                          name.replace(" workshops", ""), name.replace(" licenses", "")}:
                self.cat_alias[_norm(alias)] = name

    def category(self, raw):
        k = _norm(raw)
        if k in self.cat_alias:
            return self.categories[self.cat_alias[k]]
        for a, n in self.cat_alias.items():
            if a in k or k in a:
                return self.categories[n]
        raise KeyError(raw)

    # ------------------------------------------------------------- suppliers
    def _load_suppliers(self):
        d = os.path.join(self.root, "suppliers")
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            txt = open(os.path.join(d, fn), encoding="utf-8").read()
            name = re.search(r"#\s*Supplier:\s*(.+)", txt).group(1).strip()
            status_line = re.search(r"\*\*Status:\*\*\s*(.+)", txt).group(1)
            status = "APPROVED"
            if "BLACKLIST" in status_line.upper():
                status = "BLACKLISTED"
            elif "PROBATION" in status_line.upper():
                status = "PROBATION"
            sup = {"name": name, "status": status, "caps": {}, "fx": {}}
            for cm in re.finditer(r"\*\*Contract:\*\*\s*(.+)", txt):
                c = cm.group(1)
                m = re.search(r"invoices in ([A-Z]{3}) are converted at ₹([\d,\.]+)", c)
                if m:
                    sup["fx"][m.group(1)] = _num(m.group(2))
                m = re.search(r"price cap for (.+?) of ₹([\d,\.]+)", c)
                if m:
                    sup["caps"][m.group(1).strip()] = _num(m.group(2))
            self.suppliers[name] = sup
            self.sup_alias[_norm(name)] = name
            self.sup_alias[_norm(fn[:-3])] = name

    def supplier(self, raw):
        k = _norm(raw)
        if k in self.sup_alias:
            return self.suppliers[self.sup_alias[k]]
        k2 = k.replace(" and ", " ")
        for a, n in self.sup_alias.items():
            if a.replace(" and ", " ") == k2:
                return self.suppliers[n]
        return None  # unknown supplier -> treated as approved, no contract

    # ------------------------------------------------------------ amendments
    def _load_amendments(self):
        d = os.path.join(self.root, "amendments")
        fieldmap = {"walk-away price": "walkaway", "target price": "target",
                    "approval limit": "limit", "gst rate": "gst",
                    "negotiation rounds": "R", "concession exponent": "beta"}
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            txt = open(os.path.join(d, fn), encoding="utf-8").read()
            date = re.search(r"Effective from:\*\*\s*(\d{4}-\d{2}-\d{2})", txt).group(1)
            ch = re.search(r"\*\*Change:\*\*\s*the (.+?) for (.+?) is now (.+?)\.?\s*$",
                           txt, re.M)
            field_txt, cat_txt, val_txt = ch.group(1).lower(), ch.group(2), ch.group(3)
            fld = None
            for k, v in fieldmap.items():
                if field_txt.startswith(k):
                    fld = v
            val = _num(re.sub(r"[^\d,\.%₹]", "", val_txt))
            if fld == "gst":
                val = val / 100
            if fld == "R":
                val = int(val)
            self.amendments.append({"id": fn[:-3], "date": date,
                                    "category": self.category(cat_txt)["name"],
                                    "field": fld, "value": val})

    # --------------------------------------------------------- values in force
    def params(self, cat_name, date, supplier):
        """Category values in force for a thread on `date` (YYYY-MM-DD).

        Category page -> amendments effective on/before the date, applied in
        order of effective date (a later-dated amendment replaces an earlier
        one) -> supplier contract (price cap replaces walk-away; contract FX
        replaces table FX).
        """
        base = dict(self.categories[cat_name])
        applicable = [a for a in self.amendments
                      if a["category"] == cat_name and a["date"] <= date]
        applicable.sort(key=lambda a: (a["date"], a["id"]))
        base["applied"] = []
        for a in applicable:
            base[a["field"]] = a["value"]
            base["applied"].append(a["id"])
        base["fx_override"] = {}
        if supplier:
            for cname, cap in supplier["caps"].items():
                if self.category(cname)["name"] == cat_name:
                    base["walkaway"] = cap
                    base["applied"].append("CAP")
            base["fx_override"] = dict(supplier["fx"])
        return base
