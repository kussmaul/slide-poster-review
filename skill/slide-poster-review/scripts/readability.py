"""Measure readability (rubric items RD-1 to RD-3) and report secondary signals.

Usage:
    python scripts/readability.py OUTPUT_DIR [--audience general|l2|experts] [--lang en]

Needs manifest.json and text.json (render.py, extract_text.py). Writes OUTPUT_DIR/readability.json
(same layout as font_size.json: items, findings, notices, units) plus `signals` (formula scores)
and `hints` (evidence for the judged item RD-4).

Text: body text on shown pages, i.e. titles, bullets, labels, and chart text, but not footers,
citations, or superscripts (font_size.assign_roles). Text found by OCR is left out: misread words
would count as rare words.

RD-1  Vocabulary level. Each word is looked up in the CEFR-J Wordlist (A1-B2) and the Octanove
      C1/C2 list (assets/cefr/), after removing inflections (-s, -ed, -ing, -er, -est, -ly, and
      common irregular forms). Words in neither list count as above every level. Names (words
      capitalized everywhere in the deck and in no list), numbers, and acronyms are left out.
      Coverage = share of the remaining running words at or below the audience's target level.
      Bounds follow vocabulary coverage research (Laufer 1989; Hu & Nation 2000; Laufer &
      Ravenhorst-Kalovski 2010; Schmitt et al. 2011):
        Level 4  98% or more (adequate unassisted comprehension)
        Level 3  95% or more (minimal comprehension, with some support)
        Level 2  90% or more
        Level 1  under 90%
      Pooled over the deck (a slide has too few words for a stable share), so per-slide numbers
      are only used to say where the words are.

RD-2  Sentence length. Sentences are split at . ? ! ; : and at bullets. A slide's level is set
      by its longest sentence; item level = level reached by 90% of slides (as for FS-1).
        Level 4  15 words or fewer
        Level 3  20 or fewer (plain-language guidance: 15-20 words on average)
        Level 2  30 or fewer
        Level 1  more than 30

RD-3  Acronyms defined. Distinct acronyms (2-7 capitals, e.g. TPS, LLMs) with no expansion
      anywhere in the shown text, as "Think-Pair-Share (TPS)", "TPS (Think-Pair-Share)",
      "TPS = ..." or "TPS: ...". Acronyms in the CEFR lists (TV, DNA) and a few common ones
      (PDF, USA) are exempt.
        Level 4  none undefined
        Level 3  1-2
        Level 2  3-5
        Level 1  6 or more

Secondary signals (not scored): Flesch Reading Ease and Flesch-Kincaid grade, over sentences of
3+ words. Slides are fragments, so these read as easier than the text is. Flesch has adaptations
for de, es, fr, it, nl, ru (constants as in textstat 0.7.13); Flesch-Kincaid is English only.
Syllables are counted as vowel groups. CEFR items need English; for other languages RD-1 is not
assessed.

Audience (from intake) sets the RD-1 target level: general = B2 (default), l2 = B1 (readers of
English as a second language), experts = C2 (only words in neither list count).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_size as fs  # noqa: E402  (roles, kinds, item percentile)

SKILL = Path(__file__).resolve().parents[1]
CEFR_FILES = ("cefrj-vocabulary-profile-1.5.csv", "octanove-vocabulary-profile-c1c2-1.0.csv")
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
OFF_LIST = 6  # rank for words in neither list
AUDIENCES = {"general": "B2", "l2": "B1", "experts": "C2"}
COVERAGE_BOUNDS = (0.90, 0.95, 0.98)   # L2, L3, L4 lower bounds
SENTENCE_BOUNDS = (30, 20, 15)         # L2, L3, L4 upper bounds (words)
ACRONYM_BOUNDS = (5, 2, 0)             # L2, L3, L4 upper bounds (undefined acronyms)
MIN_SIGNAL_WORDS = 3                   # sentences shorter than this are left out of formulas
COMMON_ACRONYMS = {"OK", "US", "USA", "UK", "EU", "UN", "PDF", "URL", "FAQ", "CEO", "AM", "PM",
                   "ASAP", "FYI", "PS", "QR", "USB", "GPS", "NASA", "BBC", "NB", "VS", "AI"}
ABBREVIATIONS = {"etc": 1, "vs": 1, "eg": 1, "ie": 1, "info": 1, "app": 1, "apps": 1, "ok": 0,
                 "mr": 0, "mrs": 0, "ms": 0, "dr": 0, "st": 1, "pp": 2, "approx": 2}  # rank as A1/A2/B1
PREFIXES = {"pre", "post", "mini", "re", "un", "non", "co", "multi", "self", "inter", "sub", "semi",
            "micro", "anti", "over", "under", "sub", "meta", "cross", "e"}
NOT_NAME = re.compile(r"(tion|sion|ive|ity|ism|ist|ology|ment|ness|i[sz]e|i[sz]ation|ated|ical|ic|ous"
                      r"|ence|ance|able|ible|ary|ory)s?$")
URL_EMAIL = re.compile(r"\S+@\S+|https?://\S+|www\.\S+|\b\S+\.(?:org|com|edu|net|gov|io)\b\S*", re.I)
ROMAN = re.compile(r"^(?=[IVXLC]{2,}$)C{0,3}(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
STOP = {"of", "and", "&", "the", "for", "in", "to", "a", "an", "on", "with", "by", "or", "at"}
PARTICLES = {"up", "out", "off", "down", "back", "away", "apart", "aside"}

# Flesch Reading Ease constants (base, per word-per-sentence, per syllable-per-word)
FLESCH = {"en": (206.835, 1.015, 84.6, "Flesch Reading Ease"),
          "de": (180, 1.0, 58.5, "Flesch (Amstad)"),
          "es": (206.84, 1.02, 60.0, "Fernandez Huerta"),
          "fr": (207, 1.015, 73.6, "Flesch (Kandel & Moles)"),
          "it": (217, 1.3, 60.0, "Flesch-Vacca"),
          "nl": (206.835, 0.93, 77, "Flesch-Douma"),
          "ru": (206.835, 1.3, 60.1, "Flesch (Oborneva)")}
VOWELS = {"en": "aeiouy", "de": "aeiouyäöü", "es": "aeiouáéíóúü", "fr": "aeiouyàâéèêëîïôûùü",
          "it": "aeiouàèéìíòóù", "nl": "aeiouy", "ru": "аеёиоуыэюя"}
COMMON_EN = {"the", "and", "of", "to", "a", "in", "is", "for", "that", "with", "on", "are", "be",
             "this", "it", "as", "or", "you", "your", "can", "how", "what", "we", "by", "an"}

IRREGULAR = dict(p.split(":") for p in (
    "was:be were:be been:be am:be is:be are:be has:have had:have does:do did:do done:do "
    "went:go gone:go made:make said:say saw:see seen:see took:take taken:take got:get gotten:get "
    "gave:give given:give knew:know known:know thought:think came:come found:find told:tell "
    "became:become left:leave felt:feel brought:bring began:begin begun:begin kept:keep held:hold "
    "wrote:write written:write stood:stand heard:hear meant:mean met:meet ran:run paid:pay sat:sit "
    "spoke:speak spoken:speak led:lead grew:grow grown:grow lost:lose fell:fall fallen:fall "
    "sent:send built:build understood:understand drew:draw drawn:draw broke:break broken:break "
    "spent:spend taught:teach bought:buy caught:catch chose:choose chosen:choose drove:drive "
    "driven:drive ate:eat eaten:eat forgot:forget forgotten:forget sold:sell thrown:throw threw:throw "
    "wore:wear worn:wear won:win shown:show rose:rise risen:rise sought:seek fought:fight "
    "children:child men:man women:woman feet:foot teeth:tooth mice:mouse people:person "
    "better:good best:good worse:bad worst:bad data:datum criteria:criterion analyses:analysis "
    "hypotheses:hypothesis phenomena:phenomenon theses:thesis").split())

WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’](?=[^\W\d_]))*(?:-[^\W\d_]+)*|\d+(?:[.,]\d+)*(?:%|st|nd|rd|th|s)?")
BULLET_GLYPHS = "●○■□◆◇▪▫•◦‣∙➢➤►▸✓✔"
INLINE_BULLET = re.compile(f"[{BULLET_GLYPHS}]")
SENT_END = re.compile(r"(?<=[.!?;:])\s+|\s+[–—]\s+")
ACRONYM = re.compile(r"^[A-Z][A-Z0-9&]*[A-Z0-9](s)?$")


# ---------- word list ----------

LIST_ACRONYMS: set = set()  # acronyms that are headwords in the lists (TV, DNA): filled by load_wordlist
PHRASE_HEADS: dict = {}     # first words of multiword entries ("according" to): filled by load_wordlist


def load_wordlist(skill: Path = SKILL) -> tuple[dict, dict]:
    """({word: (rank, pos set)}, {phrase: rank}) from the CEFR files; rank 0 = A1 ... 5 = C2."""
    words: dict = {}
    phrases: dict = {}
    for name in CEFR_FILES:
        with open(skill / "assets" / "cefr" / name, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                level = (row.get("CEFR") or "").strip().upper()
                if level not in LEVELS:
                    continue
                rank = LEVELS.index(level)
                for form in row["headword"].split("/"):
                    form = form.strip()
                    if not form:
                        continue
                    key = form.lower()
                    if form.isupper() and len(form) > 1:
                        LIST_ACRONYMS.add(form)
                    if " " in key:
                        phrases[key] = min(rank, phrases.get(key, OFF_LIST))
                        head = key.split()[0]
                        PHRASE_HEADS[head] = min(rank, PHRASE_HEADS.get(head, OFF_LIST))
                        continue
                    old = words.get(key)
                    pos = {row.get("pos", "").strip()}
                    words[key] = (min(rank, old[0]), old[1] | pos) if old else (rank, pos)
    return words, phrases


def _candidates(w: str):
    if w in IRREGULAR:
        yield IRREGULAR[w]
    for end in ("'s", "’s", "s'", "s’"):
        if w.endswith(end):
            w = w[:-2] if end[0] in "'’" else w[:-1]
            yield w
    rules = (("ies", "y"), ("ied", "y"), ("ier", "y"), ("iest", "y"), ("ily", "y"), ("ves", "f"),
             ("ves", "fe"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""),
             ("ing", "e"), ("er", ""), ("er", "e"), ("est", ""), ("est", "e"), ("ly", ""),
             ("ly", "le"), ("ally", ""))
    for suf, rep in rules:
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            stem = w[: -len(suf)]
            yield stem + rep
            if not rep and len(stem) >= 3 and stem[-1] == stem[-2] and stem[-1] not in "aeiouls":
                yield stem[:-1]  # stopped -> stop, running -> run


def lookup(word: str, words: dict) -> int | None:
    """CEFR rank (0-5) of a lowercase word, or None if it's in neither list."""
    word = word.replace("’", "'")
    if word in words:  # "learning" is B2 as a noun, but a reader who knows "learn" (A1) can read it
        return min([words[word][0]] + [words[c][0] for c in _candidates(word) if c in words])
    if word in ABBREVIATIONS:
        return ABBREVIATIONS[word]
    if m := re.match(r"^(\w+)(n't|'ve|'re|'ll|'d|'m|'s)$", word):
        base = {"ca": "can", "wo": "will", "sha": "shall"}.get(m.group(1), m.group(1))
        return lookup(base, words)
    ranks = [words[c][0] for c in _candidates(word) if c in words]
    if ranks:
        return min(ranks)
    if "-" in word:
        parts = [p for p in word.split("-") if p]
        content = [p for p in parts if p not in PREFIXES] or parts
        ranks = [lookup(p, words) for p in content]
        if ranks and all(r is not None for r in ranks):
            return max(ranks)
    if word in PHRASE_HEADS:
        return PHRASE_HEADS[word]
    return None


# ---------- text ----------

def _line_text(spans: list[dict]) -> str:
    out = ""
    prev = None
    for s in sorted(spans, key=lambda s: s["bbox"][0]):
        t = s["text"]
        if prev is not None and not out.endswith(" ") and not t.startswith(" "):
            gap = s["bbox"][0] - prev["bbox"][2]
            if gap > 0.15 * min(s["size_pt"], prev["size_pt"]):
                out += " "
        out += t
        prev = s
    return " ".join(out.split())


def segments(page: dict) -> list[dict]:
    """Bullets, paragraphs, and titles on a page as [{text, kind}], in reading order. A new
    segment starts at a line beginning with a bullet or list number and at inline bullet glyphs;
    wrapped lines join the segment above."""
    lines = defaultdict(list)
    for s in page["spans"]:
        if s.get("role") == "body":
            lines[(s["block"], s["line"])].append(s)
    segs: list[dict] = []
    cur_block = None
    for key in sorted(lines):
        spans = lines[key]
        text = _line_text(spans)
        kind = Counter(s.get("kind", "text") for s in spans).most_common(1)[0][0]
        starts = fs.BULLET_START.match(text) is not None
        if segs and key[0] == cur_block and not starts and segs[-1]["kind"] == kind:
            joiner = "" if segs[-1]["text"].endswith("-") else " "
            segs[-1]["text"] += joiner + text
        else:
            segs.append({"text": text, "kind": kind})
        cur_block = key[0]
    out = []
    for seg in segs:
        for part in INLINE_BULLET.split(seg["text"]):
            part = fs.BULLET_START.sub("", part, count=1).strip() if fs.BULLET_START.match(part) else part.strip()
            if re.search(r"[^\W\d_]", part):
                out.append({"text": part, "kind": seg["kind"]})
    return out


def _title_case(toks: list[str]) -> bool:
    """True for Title Case text (most longer words capitalized), where capitals don't mark names."""
    long = [t for t in toks if len(t) > 3 and not t[0].isdigit()]
    return len(long) >= 2 and sum(t[0].isupper() for t in long) >= 0.6 * len(long)


def sentences(seg_text: str) -> list[str]:
    return [s for s in SENT_END.split(seg_text) if re.search(r"[^\W\d_]", s)]


def tokens(text: str) -> list[str]:
    text = URL_EMAIL.sub(" ", text)
    return [t for t in WORD.findall(text) if len(t) > 1 or t.lower() in ("a", "i") or t.isdigit()]


def syllables(word: str, lang: str = "en") -> int:
    w = word.lower()
    vowels = VOWELS.get(lang, VOWELS["en"])
    n = len(re.findall(f"[{vowels}]+", w))
    if lang == "en":
        if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
            n -= 1
        if re.search(r"[^aeiouy]ed$", w) and not re.search(r"[td]ed$", w) and n > 1:
            n -= 1
    return max(1, n)


# ---------- acronyms ----------

def _initials(ws: list[str]) -> str:
    return "".join(w[0] for w in ws).upper()


def _expands(acr: str, ws: list[str]) -> bool:
    """True if some run of words in `ws` has initials matching the acronym, with or without
    small words like 'of' and 'and'. `ws` are the words just before (reversed) or after."""
    letters = re.sub(r"[^A-Z]", "", acr.rstrip("s"))
    parts = [p for w in ws for p in w.split("-") if p]
    for keep_stops in (False, True):
        seq = [p for p in parts if keep_stops or p.lower() not in STOP]
        if _initials(seq[: len(letters)]) == letters:
            return True
    return False


def defined_acronyms(text: str) -> set[str]:
    """Acronyms that are expanded somewhere in `text`."""
    out = set()
    for m in re.finditer(r"\(([A-Z][A-Za-z0-9&]*[A-Z0-9]s?)\)", text):  # expansion (ABC)
        before = WORD.findall(text[max(0, m.start() - 160):m.start()])
        acr = m.group(1).rstrip("s")
        n = len(re.sub(r"[^A-Z]", "", acr))
        for k in range(1, min(len(before), 2 * n + 3) + 1):
            if _expands(acr, before[-k:]):
                out.add(acr)
                break
    for m in re.finditer(r"\b([A-Z][A-Z0-9&]*[A-Z0-9]s?)\s*(?:\(|=|:|–|—|-\s|stands for)\s*([^)\n]{3,160})", text):
        acr = m.group(1).rstrip("s")
        if _expands(acr, WORD.findall(m.group(2))):
            out.add(acr)
    return out


# ---------- measurement ----------

def _level(value: float, bounds: tuple, higher_is_better: bool) -> int:
    level = 1
    for i, b in enumerate(bounds):
        if (value >= b) if higher_is_better else (value <= b):
            level = i + 2
    return level


def _where(pages: list[int], kind: str) -> str:
    word = ("slide", "slides") if kind == "slides" else ("page", "pages")
    return f"{word[len(pages) != 1]} " + ", ".join(map(str, pages[:3]))


def measure(out_dir: Path, audience: str = "general", lang: str = "en", kind: str | None = None,
            audience_given: bool = True) -> Path:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "text.json").read_text(encoding="utf-8"))
    kind = kind or manifest["kind_guess"]
    hidden = {p["index"]: p["hidden"] for p in manifest["pages"]}
    fs.assign_roles(text["pages"], kind)
    fs.assign_kinds(text["pages"], text.get("pptx"))
    words, phrases = load_wordlist()
    target = AUDIENCES[audience]
    target_rank = LEVELS.index(target)
    english = lang.split("-")[0].split("_")[0].lower() == "en"
    lang_root = lang.split("-")[0].split("_")[0].lower()
    notices = []
    if not audience_given:
        notices.append({"code": "RD-AUDIENCE", "level": "info",
                        "message": f"Audience not given, so vocabulary is rated for a general audience "
                                   f"(CEFR {target}).",
                        "advice": "Say whether the audience is general, second-language readers of "
                                  "English, or experts."})

    # pass 1: segments, sentences, tokens per shown page
    pages = []
    seen_lower: set = set()
    seen_cap: set = set()
    abbrevs: set = set()     # Educ., Chem., resp.: abbreviations, skipped
    name_like: set = set()   # capitalized mid-sentence in ordinary text: evidence of a name
    all_text = []
    for p in text["pages"]:
        segs = segments(p)
        page = {"page": p["index"], "hidden": hidden.get(p["index"], False), "segments": segs}
        pages.append(page)
        if page["hidden"]:
            continue
        for seg in segs:
            all_text.append(seg["text"])
            abbrevs.update(m.lower() for m in re.findall(r"\b([A-Z][a-z]{1,5}|[a-z]{2,4})\.(?=[\s,;:)]|$)", seg["text"])
                           if lookup(m.lower(), words) is None)
            if seg["text"] != seg["text"].upper():
                toks = tokens(seg["text"])
                seen_lower.update(t for t in toks if t[0].islower())
                seen_cap.update(t for t in toks if t[0].isupper() and not t.isupper())
                for sent in sentences(seg["text"]):
                    st = tokens(sent)
                    if not _title_case(st):
                        name_like.update(t for t in st[1:] if t[0].isupper() and not t.isupper())
    seen_lower = {t.lower() for t in seen_lower}
    defined = defined_acronyms("\n".join(all_text))

    # pass 2: classify words
    vocab = Counter()            # counted running words by rank
    above = defaultdict(lambda: {"count": 0, "pages": set(), "rank": None})
    acronyms = defaultdict(lambda: {"count": 0, "pages": []})
    names = Counter()
    phrasal = defaultdict(lambda: {"count": 0, "pages": set(), "rank": None})
    sigs = {"sentences": 0, "words": 0, "syllables": 0}
    common_hits = total_words = 0
    units = []
    for page in pages:
        unit = {"page": page["page"], "hidden": page["hidden"], "words": 0, "counted": 0,
                "above_target": 0, "longest_sentence": 0, "longest_text": "", "segments": len(page["segments"]),
                "longest_segment": 0}
        for seg in page["segments"]:
            shouting = seg["text"] == seg["text"].upper()
            seg_toks = tokens(seg["text"])
            unit["longest_segment"] = max(unit["longest_segment"], len(seg_toks))
            for sent in sentences(seg["text"]):
                toks = tokens(sent)
                if len(toks) > unit["longest_sentence"] and seg["kind"] != "chart/table":
                    unit["longest_sentence"], unit["longest_text"] = len(toks), sent[:160]
                if page["hidden"]:
                    continue
                if len(toks) >= MIN_SIGNAL_WORDS and seg["kind"] not in ("title", "label"):
                    alpha = [t for t in toks if not t[0].isdigit()]
                    sigs["sentences"] += 1
                    sigs["words"] += len(alpha)
                    sigs["syllables"] += sum(syllables(t, lang_root) for t in alpha)
                lows = [t.lower() for t in toks]
                for i, t in enumerate(toks):
                    unit["words"] += 1
                    total_words += 1
                    low = lows[i]
                    common_hits += low in COMMON_EN
                    if t[0].isdigit():
                        continue
                    if not shouting and ACRONYM.match(t) and len(t) <= 8:
                        acr = t[:-1] if t.endswith("s") and t[:-1].isupper() else t
                        if acr in LIST_ACRONYMS or acr in COMMON_ACRONYMS or ROMAN.match(acr):
                            continue
                        if (acr.lower() in words or acr.lower() in seen_lower
                                or acr.capitalize() in seen_cap):
                            continue  # a word or name in capitals (AND, NOTE, CLAUDE)
                        acronyms[acr]["count"] += 1
                        if page["page"] not in acronyms[acr]["pages"]:
                            acronyms[acr]["pages"].append(page["page"])
                        continue
                    if not english:
                        continue
                    rank = lookup(low, words)
                    if rank is None and low in abbrevs:
                        continue
                    if (rank is None and t[0].isupper() and low not in seen_lower
                            and (t in name_like or _title_case(toks) or re.search(r"[a-z][A-Z]", t))
                            and not NOT_NAME.search(low)):
                        names[t] += 1
                        continue
                    rank = OFF_LIST if rank is None else rank
                    vocab[rank] += 1
                    unit["counted"] += 1
                    if rank > target_rank:
                        unit["above_target"] += 1
                        a = above[low]
                        a["count"] += 1
                        a["pages"].add(page["page"])
                        a["rank"] = rank
                    if low in PARTICLES and i > 0:
                        verb = lows[i - 1]
                        phrase = f"{verb} {low}"
                        base = next((c for c in [verb, *_candidates(verb)] if c in words), None)
                        prank = phrases.get(phrase) or (phrases.get(f"{base} {low}") if base else None)
                        if prank is not None or (base and "verb" in words[base][1]):
                            ph = phrasal[phrase]
                            ph["count"] += 1
                            ph["pages"].add(page["page"])
                            ph["rank"] = prank
        if not page["hidden"]:
            unit["RD-2"] = {"level": _level(unit["longest_sentence"], SENTENCE_BOUNDS, False)
                            if unit["longest_sentence"] else 4}
        units.append(unit)

    scored = [u for u in units if not u["hidden"] and u["words"]]
    unit_word = ("slide", "slides") if kind == "slides" else ("page", "pages")
    items, findings = {}, []

    # RD-1
    counted = sum(vocab.values())
    if english and counted:
        within = sum(n for r, n in vocab.items() if r <= target_rank)
        coverage = within / counted
        level = _level(coverage, COVERAGE_BOUNDS, True)
        items["RD-1"] = {"level": level, "units": len(scored), "confidence": "medium",
                         "coverage": round(coverage, 4), "target": target, "words_counted": counted,
                         "profile": {(LEVELS[r] if r < OFF_LIST else "off-list"): n
                                     for r, n in sorted(vocab.items())}}
        if level < 4:
            top = sorted(above.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
            ex = ", ".join(f"{w} ({'off-list' if a['rank'] == OFF_LIST else LEVELS[a['rank']]}"
                           f"{', ×' + str(a['count']) if a['count'] > 1 else ''})" for w, a in top[:6])
            worst = sorted((u for u in scored if u["above_target"]),
                           key=lambda u: (-u["above_target"], u["page"]))
            above_what = ("rarer than the CEFR lists cover (above C2)" if target == "C2"
                          else f"above CEFR {target}, the level for this audience")
            headline = (f"{100 * (1 - coverage):.1f}% of words are {above_what}; comprehension "
                        "needs about 98% known words.")
            details = (f"Most frequent: {ex}. Most on {_where([u['page'] for u in worst], kind)}. "
                       "Technical terms the audience knows, or that are defined, are fine.")
            findings.append({"id": "RD-1", "level": level, "count": len(worst), "confidence": "medium",
                             "headline": headline, "details": details,
                             "summary": f"RD-1: {headline} {details}", "units": [u["page"] for u in worst]})
    else:
        items["RD-1"] = {"level": None, "units": 0}
        if not english:
            notices.append({"code": "RD-LANG", "level": "info",
                            "message": f"Vocabulary level (CEFR) wasn't rated: the word lists are English "
                                       f"and the text language is {lang}.", "advice": None})

    # RD-2
    if scored:
        levels = sorted(u["RD-2"]["level"] for u in scored)
        counts = Counter(levels)
        items["RD-2"] = {"level": levels[int(fs.ITEM_PERCENTILE * len(levels))], "units": len(scored),
                         "confidence": "medium",
                         "level_counts": {f"L{k}": counts.get(k, 0) for k in (1, 2, 3, 4)}}
        low = sorted((u for u in scored if u["RD-2"]["level"] < 3), key=lambda u: (-u["longest_sentence"], u["page"]))
        if low:
            n = len(low)
            ex = low[0]
            headline = (f"{n} {unit_word[n != 1]} {'has' if n == 1 else 'have'} sentences or bullets "
                        f"over {SENTENCE_BOUNDS[1]} words.")
            details = (f"For example: {_where(sorted(u['page'] for u in low), kind)}. Longest: "
                       f"{ex['longest_sentence']} words on {unit_word[0]} {ex['page']} "
                       f"(\"{ex['longest_text'][:60]}…\").")
            findings.append({"id": "RD-2", "level": min(u["RD-2"]["level"] for u in low), "count": n,
                             "confidence": "medium", "headline": headline, "details": details,
                             "summary": f"RD-2: {headline} {details}", "units": [u["page"] for u in low]})
    else:
        items["RD-2"] = {"level": None, "units": 0}

    # RD-3
    acr_list = [{"acronym": a, "defined": a in defined, "count": v["count"], "pages": v["pages"],
                 "first_page": v["pages"][0]} for a, v in sorted(acronyms.items(), key=lambda kv: kv[1]["pages"][0])]
    undefined = [a for a in acr_list if not a["defined"]]
    if scored:
        level = _level(len(undefined), ACRONYM_BOUNDS, False)
        items["RD-3"] = {"level": level, "units": len(scored), "confidence": "medium",
                         "acronyms": len(acr_list), "undefined": len(undefined)}
        if undefined:
            n = len(undefined)
            shown = sorted(undefined, key=lambda a: -a["count"])[:6]
            headline = f"{n} acronym{'s are' if n != 1 else ' is'} used without being spelled out."
            details = ("For example: " + ", ".join(f"{a['acronym']} ({unit_word[0]} {a['first_page']})"
                                                   for a in shown) +
                       ". The audience may know some of these.")
            findings.append({"id": "RD-3", "level": level, "count": n, "confidence": "medium",
                             "headline": headline, "details": details,
                             "summary": f"RD-3: {headline} {details}",
                             "units": sorted({a["first_page"] for a in undefined})})
    else:
        items["RD-3"] = {"level": None, "units": 0}

    # secondary signals
    signals = {"lang": lang, "sentences": sigs["sentences"], "words": sigs["words"]}
    if sigs["sentences"] and sigs["words"]:
        wps = sigs["words"] / sigs["sentences"]
        spw = sigs["syllables"] / sigs["words"]
        signals.update(words_per_sentence=round(wps, 1), syllables_per_word=round(spw, 2))
        if lang_root in FLESCH:
            base, a, b, name = FLESCH[lang_root]
            signals["flesch"] = {"formula": name, "score": round(base - a * wps - b * spw, 1)}
        if english:
            signals["flesch_kincaid_grade"] = round(0.39 * wps + 11.8 * spw - 15.59, 1)
    if english and total_words >= 50 and common_hits / total_words < 0.08:
        notices.append({"code": "RD-LANG-GUESS", "level": "warning",
                        "message": "The text may not be English; vocabulary results may be wrong.",
                        "advice": "Give the language, e.g. --lang de."})
    ocr_words = 0
    try:
        ocr_words = len(json.loads((out_dir / "ocr.json").read_text(encoding="utf-8"))["words"])
    except (FileNotFoundError, KeyError):
        pass
    if ocr_words:
        notices.append({"code": "RD-OCR", "level": "info",
                        "message": f"Readability leaves out the {ocr_words} words found by OCR in images.",
                        "advice": None})

    hints = {
        "above_target": [{"word": w, "level": "off-list" if a["rank"] == OFF_LIST else LEVELS[a["rank"]],
                          "count": a["count"], "pages": sorted(a["pages"])[:8]}
                         for w, a in sorted(above.items(), key=lambda kv: (-kv[1]["count"], kv[0]))[:60]],
        "names_skipped": [w for w, _ in names.most_common(40)],
        "acronyms": acr_list,
        "phrasal_verbs": [{"phrase": p, "level": LEVELS[v["rank"]] if v["rank"] is not None else None,
                           "count": v["count"], "pages": sorted(v["pages"])[:8]}
                          for p, v in sorted(phrasal.items(), key=lambda kv: -kv[1]["count"])[:30]],
        "long_sentences": [{"page": u["page"], "words": u["longest_sentence"], "text": u["longest_text"]}
                           for u in sorted(scored, key=lambda u: -u["longest_sentence"])[:10]
                           if u["longest_sentence"] > SENTENCE_BOUNDS[1]],
    }
    findings.sort(key=lambda f: (f["level"], -f["count"]))
    result = {"measure": "readability", "kind": kind, "audience": audience, "target": target, "lang": lang,
              "thresholds": {"coverage": COVERAGE_BOUNDS, "sentence_words": SENTENCE_BOUNDS,
                             "undefined_acronyms": ACRONYM_BOUNDS},
              "items": items, "findings": findings, "notices": notices, "signals": signals,
              "hints": hints, "units": units}
    path = out_dir / "readability.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--audience", choices=sorted(AUDIENCES),
                    help="general (CEFR B2, default), l2 (B1: English as a second language), experts (C2)")
    ap.add_argument("--lang", default="en", help="text language, e.g. en, de, es (default en)")
    ap.add_argument("--kind", choices=["slides", "poster"])
    a = ap.parse_args(argv)
    try:
        path = measure(a.out_dir, a.audience or "general", a.lang, a.kind, audience_given=a.audience is not None)
    except (KeyError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    res = json.loads(path.read_text(encoding="utf-8"))
    for iid, it in res["items"].items():
        extra = it.get("coverage", it.get("level_counts", it.get("undefined", "")))
        print(f"{iid}: level {it['level']}  {extra}")
    sig = res["signals"]
    if "flesch" in sig:
        print(f"signals: {sig['flesch']['formula']} {sig['flesch']['score']}, "
              f"FK grade {sig.get('flesch_kincaid_grade', '-')}, {sig['words_per_sentence']} words/sentence")
    for f in res["findings"]:
        print(f["summary"])
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles and pipes default to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
