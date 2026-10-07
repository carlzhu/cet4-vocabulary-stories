"""Build a self-contained typing game web page from the protected vocabulary.

The page is a single HTML file - open it by double-clicking, no server and no build
step - because a learning resource is more useful when it can be handed to someone. All
6,127 CET-4 targets are embedded, each tagged with the chapter that introduces it, so
practice can be limited to the chapter or arc being read instead of the whole list.

The markup, styles and game code live in ``game/template.html`` and are injected with
data here. Keeping them in a real HTML file means the JavaScript is written as
JavaScript, not as a Python string with doubled braces.

Data notes:

* the gloss takes the **first line** of ``chinese_meaning``. That field is
  ``POS. gloss\\nPOS2. gloss2`` with ECDICT noise after it, and the first line is the
  clean, useful part.
* lemmas repeat across entries in a few cases; the survivor is the one whose chapter
  comes first, so a word is practised when the curriculum introduces it.
* the JSON escapes ``<`` so no lemma or gloss can terminate the script tag early.

Key words (``k``). The page can drill a chapter's hardest words instead of all 45, and
the definition was measured rather than assumed. The obvious signal - ECDICT frequency
metadata (Collins stars, Oxford 3000) - was rejected: it flags 1,051 words of five
letters or fewer (``I``, ``a``, ``about``, ``yes``) and misses 1,105 words of nine
letters or more (``accommodate``, ``characterize``). For a *typing* game the useful axis
is spelling load, which is inherent to the syllabus rather than derivable from word
frequency:

    key  =  len(lemma) >= 9  or  (len(lemma) >= 7 and (Oxford 3000 or Collins >= 4))

Measured over the corpus that flags 2,439 of 6,127 words - 17.8 per chapter, minimum 5 -
admits **no word shorter than seven letters**, and misses no long word. Within a chapter
the words are emitted key-first and longest-first, so a round starts with the words that
need the practice without any client-side sorting.

Usage:
    python build/make_typing_game.py                  # writes CET4_Typing_Game.html
    python build/make_typing_game.py --out game.html
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MASTER = ROOT / "vocabulary_master.csv"
PLAN = ROOT / "curriculum_plan.csv"
TEMPLATE = ROOT / "game" / "template.html"
DEFAULT_OUT = ROOT / "CET4_Typing_Game.html"
TOTAL_TARGETS = 6127
GLOSS_LIMIT = 34
SHORT_LIMIT = 14
# A key-word drill shorter than this is not worth starting, so a chapter whose key set is
# thinner is topped up from its longest remaining words. Only 2 chapters come close.
KEY_FLOOR = 6
KEY_MIN_LENGTH = 9
KEY_CORE_MIN_LENGTH = 7


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def gloss(value: str, limit: int = GLOSS_LIMIT) -> str:
    """First line of chinese_meaning, which is the part-of-speech and gloss."""

    text = value.replace("\\r\\n", "\n").replace("\\n", "\n").split("\n")[0]
    text = text.replace(" || ", "；").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def short_gloss(value: str, limit: int = SHORT_LIMIT) -> str:
    """A one-sense gloss for the line under a falling word.

    The full gloss is a dictionary entry - ``n. 原料, 要素, 东西, 材料, 素质, 织品,
    废物, 废话`` - and three lines of that stacked under each falling word would be
    unreadable. The line under the word keeps the part of speech and the **first sense**,
    which is what recognition practice needs; the full gloss still appears in the hint bar
    for the word being typed.
    """

    text = value.replace("\\r\\n", "\n").replace("\\n", "\n").split("\n")[0]
    text = text.replace(" || ", "；").strip()
    part = ""
    marker = re.match(r"^([A-Za-z]{1,6}\.\s*)", text)
    if marker:
        part = marker.group(1)
        text = text[marker.end():]
    sense = re.split(r"[,，;；、]", text)[0].strip()
    combined = (part + sense).strip()
    if len(combined) <= limit:
        return combined
    return combined[: limit - 1].rstrip() + "…"


def is_core(entry: dict[str, str]) -> bool:
    """Oxford 3000, or a Collins rating of 4 or 5."""

    collins = str(entry.get("ecdict_collins", "")).strip()
    stars = int(collins) if collins.isdigit() else 0
    return str(entry.get("ecdict_oxford", "")).strip() == "1" or stars >= 4


def is_key(lemma: str, entry: dict[str, str]) -> bool:
    """The documented key-word rule; see the module docstring for why it is length-led."""

    length = len(lemma)
    return length >= KEY_MIN_LENGTH or (length >= KEY_CORE_MIN_LENGTH and is_core(entry))


def build_payload() -> dict[str, object]:
    master = read_csv(MASTER)
    plan = read_csv(PLAN)
    if len(master) != TOTAL_TARGETS:
        raise SystemExit(f"expected {TOTAL_TARGETS} targets, found {len(master)}")

    by_id = {row["vocabulary_id"]: row for row in master}
    chapters: list[dict[str, object]] = []
    words: dict[str, dict[str, object]] = {}
    unmapped: list[str] = []

    for row in sorted(plan, key=lambda r: int(r["chapter_number"])):
        number = int(row["chapter_number"])
        arc = int(row["arc_number"])
        chapters.append(
            {
                "n": number,
                "t": row["english_title"],
                "z": row["chinese_title"],
                "m": row["theme"],
                "a": arc,
            }
        )
        for vocabulary_id in (row["new_vocabulary_ids"] or "").split("|"):
            if not vocabulary_id:
                continue
            entry = by_id.get(vocabulary_id)
            if entry is None:
                unmapped.append(vocabulary_id)
                continue
            lemma = entry["lemma"].strip()
            key = lemma.lower()
            if key in words:
                continue  # the earliest chapter introduces it, so it wins
            words[key] = {
                "w": lemma,
                "p": (entry["phonetic"] or "").strip(),
                "m": gloss(entry["chinese_meaning"] or ""),
                "s": short_gloss(entry["chinese_meaning"] or ""),
                "c": number,
                "a": arc,
                "k": 1 if is_key(lemma, entry) else 0,
            }

    if unmapped:
        raise SystemExit(f"{len(unmapped)} planned ids are missing from the master")

    # Key words first, then longest first, then alphabetically. A chapter pool therefore
    # arrives in the order it should be practised, with no client-side sorting.
    ordered = sorted(
        words.values(),
        key=lambda w: (int(w["c"]), -int(w["k"]), -len(str(w["w"])), str(w["w"]).lower()),
    )

    per_chapter: dict[int, int] = {}
    for word in ordered:
        if word["k"]:
            per_chapter[int(word["c"])] = per_chapter.get(int(word["c"]), 0) + 1
    for chapter in chapters:
        chapter["kn"] = per_chapter.get(int(chapter["n"]), 0)

    return {
        "words": ordered,
        "chapters": chapters,
        "targets": len(master),
        "unique": len(ordered),
        "duplicates": len(master) - len(ordered),
        "key_total": sum(1 for w in ordered if w["k"]),
        "key_rule": (
            f"{KEY_MIN_LENGTH} letters or more, or a {KEY_CORE_MIN_LENGTH}-{KEY_MIN_LENGTH - 1} "
            f"letter Oxford 3000 / Collins 4-5 word"
        ),
        "key_floor": KEY_FLOOR,
    }


def render(payload: dict[str, object]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )
    template = TEMPLATE.read_text(encoding="utf-8")
    chapters = payload["chapters"]
    rendered = (
        template.replace("__WORD_DATA__", data)
        .replace("__TARGETS__", str(payload["targets"]))
        .replace("__UNIQUE__", str(payload["unique"]))
        .replace("__CHAPTERS__", str(len(chapters)))
        .replace("__ARCS__", str(len({c["a"] for c in chapters})))
    )
    for placeholder in ("__WORD_DATA__", "__TARGETS__", "__UNIQUE__", "__CHAPTERS__", "__ARCS__"):
        if placeholder in rendered:
            raise SystemExit(f"template placeholder {placeholder} was not substituted")
    return rendered


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv[1:])

    payload = build_payload()
    target = pathlib.Path(args.out)
    target.write_text(render(payload), encoding="utf-8")

    words = payload["words"]
    print(f"  targets in master : {payload['targets']}")
    print(
        f"  unique lemmas     : {payload['unique']} "
        f"({payload['duplicates']} duplicate rows collapsed, earliest chapter kept)"
    )
    print(
        f"  chapters / arcs   : {len(payload['chapters'])} / "
        f"{len({w['a'] for w in words})}"
    )
    keyed = [int(c["kn"]) for c in payload["chapters"]]
    print(
        f"  key words         : {payload['key_total']} total "
        f"({payload['key_total'] / payload['unique'] * 100:.1f}%), "
        f"{sum(keyed) / len(keyed):.1f} per chapter, min {min(keyed)}, max {max(keyed)}"
    )
    print(f"  key rule          : {payload['key_rule']}")
    print(f"  words with gloss  : {sum(1 for w in words if w['m'])}")
    print(f"  words with IPA    : {sum(1 for w in words if w['p'])}")
    short = [w for w in words if w["s"]]
    print(f"  short glosses     : {len(short)} (for the line under each falling word)")
    for sample in short[:4]:
        print(f"      {sample['w']:14} {sample['s']:16} <- {sample['m']}")
    print(f"  written           : {target.name} ({target.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
