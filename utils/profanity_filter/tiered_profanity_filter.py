"""
Tiered profanity filter — dependency-free matching core.

Changes from the better_profanity-backed version:

  - Matching is now a plain, transparent, in-house implementation instead
    of wrapping better_profanity. After our own normalization (leetspeak,
    homoglyphs, separator-stripping, repeat-collapsing), all that's left
    is "does this normalized string match a known bad root (or root+
    suffix)", which a set lookup does in O(1). No more paying for a
    heavier general-purpose scanner, and no more risk of the empty-
    wordlist-loads-library-defaults footgun -- there's no library default
    to fall back to anymore. better_profanity is no longer a dependency.

  - Suffix-aware matching: "fuck" now also catches "fucking" / "fucker" /
    "fuckers" / "fucked" / "fucks" -- previously only the exact root
    matched. Real trade-off: it also catches "damning" off "damn" and
    "pricked" off "prick", both ordinary non-profane words. A few known
    collisions are pre-added to ALLOWLIST; expect to find more via the
    new `on_match` hook once this sees real traffic, and add them as
    they turn up. Set `allow_suffixes=False` to disable this and go back
    to exact-only matching if you'd rather not make that trade.

  - Multi-word phrase support: wordlist entries with spaces in them (e.g.
    "son of a bitch") are matched as phrases. Still exact matching under
    the hood, so this does NOT reopen the "pass hit" -> "passhit" false-
    merge problem -- there's no substring search anywhere in this file.

  - `on_match` hook: an optional callable(fragment, category) fired on
    every match, so you can log real hits/misses and use them to tune
    the wordlist and allowlist over time instead of guessing.

Wordlist: wordlist_sample.json (a STARTER file -- see the bottom of this
file for free sources to expand it).
"""
import json
import re
import unicodedata
from enum import IntEnum
from pathlib import Path

# --------------------------------------------------------------------------
# Severity / strictness
# --------------------------------------------------------------------------


class Severity(IntEnum):
    MILD = 1        # damn, hell, crap
    MODERATE = 2    # ass, bitch, shit
    SEVERE = 3       # fuck and its family


class Strictness(IntEnum):
    """Presets. Lower value = catches more (checked as `category >= level`)."""
    LENIENT = Severity.SEVERE     # "only the most extreme content"
    STANDARD = Severity.MODERATE  # "all (common) vulgarities"
    STRICT = Severity.MILD        # "nothing you wouldn't say in Congress"


SLUR = "slur"  # category flag, deliberately not on the Severity scale

# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------

LEET = {
    "@": "a", "4": "a", "^": "a",
    "3": "e",
    "1": "i", "!": "i", "|": "i",
    "0": "o",
    "$": "s", "5": "s",
    "7": "t", "+": "t",
    "8": "b",
    "9": "g",
}
HOMOGLYPHS = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c",
    "х": "x", "у": "y", "к": "k", "м": "m", "т": "t",
    "α": "a", "ο": "o", "τ": "t", "υ": "y",
}
LEET.update(HOMOGLYPHS)

SEPARATOR_CHARS = set(" \t\n\r._-,'\"`~^") | {"\u200b", "\u200c", "\u200d", "\ufeff"}

ALLOWLIST = {
    "class", "classes", "classic", "classy", "classroom",
    "assassin", "assassinate", "assassination",
    "assist", "assistant", "assistance", "assignment", "assignments",
    "grass", "brass", "glass", "bass", "compass", "surpass",
    "scunthorpe", "therapist", "cockpit", "cockburn", "cockatoo",
    "password", "passage", "passenger",
    "damning", "darning", "pricked", "pricking", "hellish",
}


def _normalize(fragment):
    out = []
    for ch in fragment:
        ch = LEET.get(ch, ch)
        ch = ch.lower()
        if ch in SEPARATOR_CHARS:
            continue
        out.append(ch)
    return "".join(out)


_normalize_cache = {}


def _normalize_cached(fragment):
    result = _normalize_cache.get(fragment)
    if result is None:
        result = _normalize(fragment)
        _normalize_cache[fragment] = result
    return result


def _collapse(s, max_run):
    out = []
    run_char, run_len = None, 0
    for ch in s:
        run_len = run_len + 1 if ch == run_char else 1
        run_char = ch
        if run_len <= max_run:
            out.append(ch)
    return "".join(out)


def _variants(fragment):
    base = _normalize_cached(fragment)
    if not base:
        return ()
    return (base, _collapse(base, 1), _collapse(base, 2))


class WordMatcher:
    SUFFIXES = ("s", "es", "ed", "er", "ers", "ing", "y")
    MIN_ROOT_LEN_FOR_SUFFIXES = 3

    def __init__(self, words, allow_suffixes=True):
        raw = [w.strip().lower() for w in words if w.strip()]
        self.max_phrase_words = max((len(w.split()) for w in raw), default=1)
        roots = {_normalize(w) for w in raw}
        expanded = set(roots)
        if allow_suffixes:
            for root in roots:
                if len(root) >= self.MIN_ROOT_LEN_FOR_SUFFIXES:
                    expanded.update(root + suf for suf in self.SUFFIXES)
        self._words = expanded
        self.has_words = bool(self._words)

    def matches(self, fragment):
        if not self.has_words:
            return False
        return any(v in self._words for v in _variants(fragment))


def _tokens(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _single_and_spelled_out_spans(tokens, text):
    spans = []
    i, n = 0, len(tokens)
    while i < n:
        start, end = tokens[i]
        spans.append((start, end))
        if len(_normalize_cached(text[start:end])) == 1:
            j, last_end = i + 1, end
            while j < n and len(_normalize_cached(text[tokens[j][0]:tokens[j][1]])) == 1:
                last_end = tokens[j][1]
                j += 1
            if j > i + 1:
                spans.append((start, last_end))
            i = j
        else:
            i += 1
    return spans


def _phrase_spans(tokens, max_n):
    spans = []
    for n in range(2, max_n + 1):
        for i in range(len(tokens) - n + 1):
            spans.append((tokens[i][0], tokens[i + n - 1][1]))
    return spans


def _find_spans(text, max_phrase_words=1):
    tokens = _tokens(text)
    spans = _single_and_spelled_out_spans(tokens, text)
    if max_phrase_words > 1:
        spans.extend(_phrase_spans(tokens, max_phrase_words))
    return spans


def load_wordlist(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        Severity.MILD: data.get("mild", []),
        Severity.MODERATE: data.get("moderate", []),
        Severity.SEVERE: data.get("severe", []),
        SLUR: data.get("slur", []),
    }


class TieredProfanityFilter:
    def __init__(self, wordlist_path, block_slurs=True, allow_suffixes=True, on_match=None):
        tiers = load_wordlist(wordlist_path)
        self._matchers = {
            sev: WordMatcher(tiers[sev], allow_suffixes=allow_suffixes) for sev in Severity
        }
        self._slur_matcher = WordMatcher(tiers[SLUR], allow_suffixes=allow_suffixes)
        self.block_slurs = block_slurs
        self.on_match = on_match
        self.max_phrase_words = max(
            [m.max_phrase_words for m in self._matchers.values()]
            + [self._slur_matcher.max_phrase_words]
        )

    def _classify(self, fragment):
        if self.block_slurs and self._slur_matcher.matches(fragment):
            return SLUR
        for severity in (Severity.SEVERE, Severity.MODERATE, Severity.MILD):
            if self._matchers[severity].matches(fragment):
                return severity
        return None

    def _scan(self, text, level):
        for start, end in _find_spans(text, self.max_phrase_words):
            fragment = text[start:end]
            if fragment.lower() in ALLOWLIST:
                continue
            category = self._classify(fragment)
            if category is None:
                continue
            if category == SLUR or category >= level:
                if self.on_match is not None:
                    self.on_match(fragment, category)
                yield start, end, category

    def classify_text(self, text, level=Strictness.STANDARD):
        return any(True for _ in self._scan(text, level))

    def censor(self, text, level=Strictness.STANDARD, censor_char="*"):
        text = unicodedata.normalize("NFKC", text)
        result = list(text)
        for start, end, _category in self._scan(text, level):
            for i in range(start, end):
                if not text[i].isspace():
                    result[i] = censor_char
        return "".join(result)


def review_context(text, reviewer):
    if reviewer is None:
        return None
    return reviewer(text)


def make_anthropic_reviewer(api_key, model="claude-sonnet-4-6"):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    def reviewer(text):
        prompt = (
            "You are a content-moderation classifier. Decide whether the "
            "message below contains harassment, threats, hate speech, or "
            "a breach of professional/parliamentary decorum -- even if it "
            "contains no profanity at all. "
            'Respond with ONLY strict JSON: {"flagged": true|false, "reason": "..."}.'
            f"\n\nMessage: {text!r}"
        )
        response = client.messages.create(
            model=model, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        payload = json.loads(response.content[0].text)
        return payload["flagged"], payload.get("reason", "")

    return reviewer


def test_me():
    wordlist_path = Path(__file__).parent / "wordlist_sample.json"
    hits = []
    pf = TieredProfanityFilter(wordlist_path, on_match=lambda frag, cat: hits.append((frag, cat)))

    tests = [
        ("that's such a load of crap", Strictness.LENIENT),
        ("that's such a load of crap", Strictness.STRICT),
        ("you stupid b1tch", Strictness.STANDARD),
        ("this is fucking ridiculous", Strictness.LENIENT),
        ("what a fucker", Strictness.LENIENT),
        ("f u c k this", Strictness.LENIENT),
        ("he's a real son of a bitch", Strictness.STANDARD),
        ("Pass hit the ball, then run", Strictness.STRICT),
        ("I hired a teaching assistant for my class", Strictness.STRICT),
        ("I pricked my finger sewing", Strictness.STRICT),
        ("the damning report was released", Strictness.STRICT),
    ]
    for text, level in tests:
        print(f"[{level.name:8}] {text!r:50} -> {pf.censor(text, level=level)!r}")
    print()
    print("on_match log:", hits)

def run_me(text, level=2):
    wordlist_path = Path(__file__).parent / "wordlist_sample.json"
    hits = []
    pf = TieredProfanityFilter(wordlist_path, on_match=lambda frag, cat: hits.append((frag, cat)))
    if level == 1:
        level = Strictness.LENIENT
    elif level == 3:
        level = Strictness.STRICT
    else:
        level = Strictness.STANDARD
    
    print(f"[{level.name:8}] {text!r:50} -> {pf.censor(text, level=level)!r}")
    return True if hits else False
