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

Usage:
    python build/make_typing_game.py                  # writes CET4_Typing_Game.html
    python build/make_typing_game.py --out game.html
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MASTER = ROOT / "vocabulary_master.csv"
PLAN = ROOT / "curriculum_plan.csv"
TEMPLATE = ROOT / "game" / "template.html"
DEFAULT_OUT = ROOT / "CET4_Typing_Game.html"
TOTAL_TARGETS = 6127
GLOSS_LIMIT = 34


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
                "c": number,
                "a": arc,
            }

    if unmapped:
        raise SystemExit(f"{len(unmapped)} planned ids are missing from the master")

    ordered = sorted(words.values(), key=lambda w: (int(w["c"]), str(w["w"]).lower()))
    return {
        "words": ordered,
        "chapters": chapters,
        "targets": len(master),
        "unique": len(ordered),
        "duplicates": len(master) - len(ordered),
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
    print(f"  words with gloss  : {sum(1 for w in words if w['m'])}")
    print(f"  words with IPA    : {sum(1 for w in words if w['p'])}")
    print(f"  written           : {target.name} ({target.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
