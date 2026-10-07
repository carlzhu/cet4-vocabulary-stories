"""List the untranslated English sentences, grouped by batch file.

For every paragraph where the Chinese stops short by two or more sentences, this
prints the full English paragraph, the current Chinese, and the English tail that
has no counterpart. The tail is what needs translating; keeping the existing
Chinese and appending is safer than rewriting a paragraph that is already good.

Usage:
    python build/translation_worklist.py                # summary per batch file
    python build/translation_worklist.py batch-CH002-CH005   # full detail
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.pdf_builder import load_chapters  # noqa: E402

EN_SENTENCE = re.compile(r"[^.!?]+[.!?]+|[^.!?]*$")
CN_SENTENCE = re.compile(r"[^。！？；…]+[。！？；…]+|[^。！？；…]*$")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
QUOTED_EN = re.compile(r"[“\"][^”\"]*[”\"]")


def prose_sentences(english: str) -> int:
    """Count English sentences outside quotation marks.

    Quoted speech is split into separate "sentences" by punctuation, but a Chinese
    rendering legitimately merges a quotation and its reporting clause. Counting
    only unquoted prose keeps genuine trailing omissions visible while dropping
    that false positive.
    """

    without_quotes = QUOTED_EN.sub(" ", english)
    return sum(1 for piece in EN_SENTENCE.findall(without_quotes) if piece.strip())


def split_sentences(text: str, pattern: re.Pattern[str]) -> list[str]:
    return [piece.strip() for piece in pattern.findall(text) if piece.strip()]


def plan_rows() -> dict[str, dict[str, str]]:
    return {
        row["article_id"]: row
        for row in csv.DictReader((ROOT / "curriculum_plan.csv").open(encoding="utf-8-sig"))
    }


def arc_edges() -> tuple[set[str], set[str]]:
    rows = list(plan_rows().values())
    by_arc: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_arc.setdefault(row["arc_number"], []).append(row)
    openers = {items[0]["article_id"] for items in by_arc.values()}
    closers = {items[-1]["article_id"] for items in by_arc.values()}
    return openers, closers


def gaps_for(chapter) -> list[tuple[int, str, str, str]]:
    """Return (paragraph_index, english, chinese, reason) for paragraphs needing work.

    Two criteria, because sentence counts alone miss a summary that skips middle
    content: a real sentence gap, or a density below 1.2 CJK characters per English
    word (faithful renderings sit near 1.48).
    """

    found: list[tuple[int, str, str, str]] = []
    for index, (english, chinese) in enumerate(
        zip(chapter.english_paragraphs, chapter.chinese_paragraphs), start=1
    ):
        cn = split_sentences(chinese, CN_SENTENCE)
        prose_gap = prose_sentences(english) - len(cn)
        words = len(english.split())
        density = len(CJK.findall(chinese)) / words if words else 0.0
        reasons = []
        if prose_gap >= 1:
            reasons.append(f"prose_gap={prose_gap}")
        if density < 1.2:
            reasons.append(f"density={density:.2f}")
        if reasons:
            found.append((index, english, chinese, ", ".join(reasons)))
    return found


def main(argv: list[str]) -> int:
    chapters = load_chapters(ROOT)
    openers, closers = arc_edges()
    plan = plan_rows()

    if len(argv) > 1:
        target = argv[1]
        real_only = "--real" in argv
        path = ROOT / "drafts" / "batches" / f"{target}.json"
        if target == "sample_chapters":
            path = ROOT / "drafts" / "sample_chapters.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document["chapters"]:
            chapter_id = entry["article_id"]
            chapter = chapters[chapter_id]
            gaps = gaps_for(chapter)
            if real_only:
                gaps = [row for row in gaps if "density" in row[3]]
            if not gaps:
                continue
            role = "OPENER" if chapter_id in openers else ("CLOSER" if chapter_id in closers else "")
            print("=" * 100)
            print(f"{chapter_id} {role} | arc {plan[chapter_id]['arc_number']} | {chapter.english_title}")
            for index, english, chinese, reason in gaps:
                print(f"--- paragraph {index}  [{reason}] ---")
                print(f"EN : {english}")
                print(f"CN : {chinese}")
        return 0

    totals = {"chapters": 0, "paragraphs": 0, "sentences": 0}
    for path in sorted((ROOT / "drafts" / "batches").glob("batch-*.json")) + [
        ROOT / "drafts" / "sample_chapters.json"
    ]:
        document = json.loads(path.read_text(encoding="utf-8"))
        rows: list[str] = []
        for entry in document["chapters"]:
            chapter_id = entry["article_id"]
            gaps = gaps_for(chapters[chapter_id])
            if not gaps:
                continue
            counts = sum(
                len(split_sentences(english, EN_SENTENCE)) - len(split_sentences(chinese, CN_SENTENCE))
                for _, english, chinese, _ in gaps
            )
            totals["chapters"] += 1
            totals["paragraphs"] += len(gaps)
            totals["sentences"] += counts
            role = "OPENER" if chapter_id in openers else ("CLOSER" if chapter_id in closers else "")
            rows.append(f"    {chapter_id} {role:<6} paragraphs={len(gaps)} sentences={counts}")
        if rows:
            print(f"{path.name}: {len(rows)} chapters")
            for row in rows:
                print(row)
    print()
    print("TOTAL:", totals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
