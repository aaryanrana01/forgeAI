"""Deterministic text helpers shared by retrieval, eval generation and the judge.

The judge leans on these so that "is this fact in the answer?" and "is this
number supported by the context?" do not depend on an LLM's opinion."""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into is it its
me my of on or our shall should so than that the their them then there these they this to under up upon
us was we were what when where which who whom why will with would you your yours about above after again
all also any because before being below between both each few further here just more most no nor not now
only other out over own same some such too very s t don per via within without may must
""".split())

_NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")
_WORD = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower()).strip()


def stem(tok: str) -> str:
    """Very small suffix stripper - enough to match leave/leaves, claim/claims."""
    for suf in ("ies", "ing", "ed", "es", "s"):
        if len(tok) > len(suf) + 2 and tok.endswith(suf):
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokens(text: str, *, keep_stop: bool = False) -> list[str]:
    toks = _WORD.findall(normalize(text))
    return [stem(t) for t in toks if keep_stop or t not in STOPWORDS]


def numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "sixty": 60, "hundred": 100,
}


def numbers_with_words(text: str) -> list[float]:
    vals = numbers(text)
    for w in _WORD.findall(normalize(text)):
        if w in WORD_NUMBERS:
            vals.append(float(WORD_NUMBERS[w]))
    return vals


CURRENCY = {"usd", "inr", "eur", "sgd", "rs", "dollar", "rupee", "us"}
_NUMTOK = re.compile(r"[\d.,/\-]+")


def _num_in(n: float, pool: list[float]) -> bool:
    return any(abs(n - p) <= max(0.011, abs(p) * 1e-4) for p in pool)


def fact_present(fact: str, text: str, *, token_threshold: float = 0.6) -> bool:
    """True if `fact` is stated in `text`.

    Rules (all deterministic):
      * exact normalized substring  -> present
      * every number in the fact must appear in the text (numbers are where
        small models hallucinate, so they are non-negotiable)
      * and at least `token_threshold` of the fact's content words appear
    """
    nf, nt = normalize(fact), normalize(text)
    if not nf:
        return True
    if nf in nt:
        return True
    fact_nums = numbers(fact)
    text_nums = numbers_with_words(text)
    if fact_nums and not all(_num_in(n, text_nums) for n in fact_nums):
        return False
    # words only: numbers were checked above, currency words are optional ("USD 1,245.50" == "1245.5 dollars")
    ftoks = {t for t in tokens(fact) if not _NUMTOK.fullmatch(t) and t not in CURRENCY}
    if not ftoks:
        return bool(fact_nums)
    ttoks = set(tokens(text))
    overlap = len(ftoks & ttoks) / len(ftoks)
    # facts that are mostly a number ("21 working days") need the number + about half the unit words
    if fact_nums and len(ftoks) <= 2:
        return overlap >= 0.5
    return overlap >= token_threshold


def unsupported_numbers(answer: str, evidence: str, question: str = "") -> list[float]:
    """Numbers in the answer that appear nowhere in the evidence or the question.
    Trivial numbers (0, 1, 2) and list markers are ignored."""
    pool = numbers_with_words(evidence) + numbers_with_words(question)
    bad = []
    for n in numbers(answer):
        if n in (0.0, 1.0, 2.0):
            continue
        if not _num_in(n, pool):
            bad.append(n)
    return bad


def jaccard(a: str, b: str) -> float:
    sa, sb = set(tokens(a)), set(tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def ngram_overlap(needle: str, haystack: str, n: int = 4) -> float:
    """Share of the needle's word n-grams that appear in the haystack. Used to
    stop the optimizer from pasting eval questions/answers into the prompt."""
    nw = tokens(needle, keep_stop=True)
    hw = tokens(haystack, keep_stop=True)
    if len(nw) < n:
        return 1.0 if " ".join(nw) and " ".join(nw) in " ".join(hw) else 0.0
    ng = {tuple(nw[i : i + n]) for i in range(len(nw) - n + 1)}
    hg = {tuple(hw[i : i + n]) for i in range(len(hw) - n + 1)}
    return len(ng & hg) / len(ng)


REFUSAL_PATTERNS = [
    r"\bi (?:can ?not|can't|am unable to|am not able to|don't have|do not have)\b",
    r"\b(?:not|isn't|is not) (?:covered|included|available|mentioned|addressed) in\b",
    r"\boutside (?:of )?(?:my|the) scope\b",
    r"\bno information (?:about|on|regarding)\b",
    r"\bplease contact\b",
    r"\bunable to (?:help|answer|assist)\b",
]


def looks_like_refusal(answer: str) -> bool:
    a = normalize(answer)
    return any(re.search(p, a) for p in REFUSAL_PATTERNS)


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = passed / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
