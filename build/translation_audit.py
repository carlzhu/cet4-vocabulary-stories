"""Measure how completely each English paragraph is rendered in Chinese.

The chapter rules require "one accurate Chinese paragraph per English paragraph".
Paragraph *counts* are aligned and validated, but that says nothing about whether
each English sentence has a Chinese counterpart. This audit compares sentence
counts per paragraph pair, because during generation several English sentences
were appended to reach the 350-word floor and were not translated.
"""

from __future__ import annotations

import re
from pathlib import Path

import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.pdf_builder import load_chapters  # noqa: E402

EN_SENTENCE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")
CN_SENTENCE = re.compile(r"[^。！？；…]+[。！？；…]+|[^。！？；…]+$")


def sentences(text: str, pattern: re.Pattern[str]) -> int:
    return sum(1 for piece in pattern.findall(text) if piece.strip())


def main() -> int:
    chapters = load_chapters(ROOT)
    plan = {
        row["article_id"]: row
        for row in csv.DictReader((ROOT / "curriculum_plan.csv").open(encoding="utf-8-sig"))
    }

    flagged: list[tuple[str, int, int, int, str]] = []
    total_pairs = 0
    gap_one = 0
    gap_real = 0
    missing_sentences = 0

    for chapter_id in sorted(chapters):
        chapter = chapters[chapter_id]
        worst = 0
        worst_index = 0
        for index, (english, chinese) in enumerate(
            zip(chapter.english_paragraphs, chapter.chinese_paragraphs), start=1
        ):
            total_pairs += 1
            en = sentences(english, EN_SENTENCE)
            cn = sentences(chinese, CN_SENTENCE)
            gap = en - cn
            if gap == 1:
                # Usually a punctuation difference: Chinese merges clauses the
                # English separates with a colon or semicolon.
                gap_one += 1
            elif gap >= 2:
                gap_real += 1
                missing_sentences += gap
            if gap > worst:
                worst = gap
                worst_index = index
        if worst >= 2:
            flagged.append(
                (chapter_id, worst, worst_index, plan[chapter_id]["arc_number"], chapter.english_title)
            )

    print(f"chapters                      : {len(chapters)}")
    print(f"paragraph pairs               : {total_pairs}")
    print(f"pairs with a 1-sentence gap   : {gap_one}  (likely punctuation artifacts)")
    print(f"pairs with a real gap (>= 2)  : {gap_real}")
    print(f"English sentences with no Chinese counterpart: {missing_sentences}")
    print(f"chapters with a real gap      : {len(flagged)}")
    print()
    print("worst gap per chapter (gap = English sentences with no Chinese counterpart):")
    for chapter_id, worst, index, arc, title in sorted(flagged, key=lambda row: -row[1]):
        print(f"  {chapter_id} (arc {arc}) gap={worst:>2} at paragraph {index} | {title}")

    if len(sys.argv) > 1 and sys.argv[1] == "--detail":
        target = sys.argv[2]
        chapter = chapters[target]
        for index, (english, chinese) in enumerate(
            zip(chapter.english_paragraphs, chapter.chinese_paragraphs), start=1
        ):
            en = sentences(english, EN_SENTENCE)
            cn = sentences(chinese, CN_SENTENCE)
            print("=" * 90)
            print(f"{target} paragraph {index}: EN sentences={en} CN sentences={cn}")
            print(f"  EN: {english}")
            print(f"  CN: {chinese}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
