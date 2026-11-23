"""Amount parsing: digits, Indian notation (lakh/crore/k) and amounts in words."""
import re
from fractions import Fraction

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "a": 1, "an": 1,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "lakhs": 100000,
          "lac": 100000, "lacs": 100000, "crore": 10**7, "crores": 10**7,
          "million": 10**6, "k": 1000}
WORDS = set(UNITS) | set(TENS) | set(SCALES) | {"and", "point", "half"}

WORD_NUM_RE = re.compile(
    r"\b(?:(?:" + "|".join(sorted((set(UNITS) - {"a", "an"}) | set(TENS), key=len, reverse=True))
    + r")(?:[\s\-]+(?:and[\s\-]+)?(?:" + "|".join(sorted(WORDS - {"half"}, key=len, reverse=True))
    + r"))*)\b", re.I)


def words_to_number(text):
    """'twenty-one thousand five hundred' -> 21500. Returns Fraction or None."""
    toks = re.split(r"[\s\-]+", text.lower().strip())
    toks = [t for t in toks if t and t != "and"]
    if not toks:
        return None
    total, current = 0, 0
    seen = False
    for t in toks:
        if t in UNITS:
            current += UNITS[t]
            seen = True
        elif t in TENS:
            current += TENS[t]
            seen = True
        elif t == "hundred":
            current = (current or 1) * 100
            seen = True
        elif t in SCALES:
            sc = SCALES[t]
            # Indian / western scales: everything accumulated so far below
            # this scale is multiplied.
            if total and total < sc and current == 0:
                total *= sc
            else:
                total += (current or 1) * sc
                current = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    return Fraction(total + current)


MULT = {"lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "l": 100000,
        "crore": 10**7, "crores": 10**7, "cr": 10**7, "k": 1000, "thousand": 1000,
        "mn": 10**6, "million": 10**6, "m": 10**6, "hundred": 100}

NUM_RE = r"(\d[\d,]*(?:\.\d+)?|\.\d+)"
MULT_RE = r"(?:\s*(lakhs?|lacs?|crores?|cr|thousand|million|mn|k|hundred)\b)?"


def parse_amount(num, mult=None):
    v = Fraction(num.replace(",", ""))
    if mult:
        v *= MULT[mult.lower()]
    return v
