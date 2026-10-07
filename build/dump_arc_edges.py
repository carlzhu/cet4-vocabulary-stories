"""Dump the arc-openers and arc-closers so their carry-over lines can be written.

For openers we need the first English paragraph and its Chinese counterpart (the
carry-over sentence goes at the front). For closers we need the last pair (the
thematic echo goes at the end). Word counts matter because every chapter must stay
within 350-450 words.
"""

from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.pdf_builder import load_chapters  # noqa: E402


def main() -> int:
    plan = list(
        csv.DictReader((ROOT / "curriculum_plan.csv").open(encoding="utf-8-sig"))
    )
    chapters = load_chapters(ROOT)

    by_arc: dict[str, list[dict[str, str]]] = {}
    for row in plan:
        by_arc.setdefault(row["arc_number"], []).append(row)

    for arc, rows in by_arc.items():
        opener_id = rows[0]["article_id"]
        closer_id = rows[-1]["article_id"]
        for role, chapter_id in (("OPENER", opener_id), ("CLOSER", closer_id)):
            chapter = chapters.get(chapter_id)
            if chapter is None:
                print(f"--- {chapter_id} {role}: MISSING")
                continue
            words = sum(len(p.split()) for p in chapter.english_paragraphs)
            print("=" * 100)
            print(
                f"arc {arc} {role} {chapter_id} | words={words} | "
                f"paras={len(chapter.english_paragraphs)}"
            )
            print(f"  EN title: {chapter.english_title}")
            if role == "OPENER":
                print(f"  EN[0]: {chapter.english_paragraphs[0]}")
                print(f"  CN[0]: {chapter.chinese_paragraphs[0]}")
            else:
                print(f"  EN[-1]: {chapter.english_paragraphs[-1]}")
                print(f"  CN[-1]: {chapter.chinese_paragraphs[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
