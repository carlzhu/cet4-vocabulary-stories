"""Estimate the true extent of the abridged-Chinese problem.

Sentence counts are a lower bound: a Chinese paragraph can skip English sentences
in the middle while ending with the same tail, so a count comparison looks small.
The giveaway is density. A faithful Chinese rendering of an English paragraph runs
roughly 1.3-1.9 Chinese characters per English word; a summary runs far less.

This prints the ratio distribution with known-good and known-bad references, so
the threshold is calibrated against real paragraphs rather than guessed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.pdf_builder import load_chapters  # noqa: E402

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def main() -> int:
    chapters = load_chapters(ROOT)
    ratios: list[tuple[float, str, int, int, int]] = []
    for chapter_id in sorted(chapters):
        chapter = chapters[chapter_id]
        for index, (english, chinese) in enumerate(
            zip(chapter.english_paragraphs, chapter.chinese_paragraphs), start=1
        ):
            words = len(english.split())
            cjk = len(CJK.findall(chinese))
            if words == 0:
                continue
            ratios.append((cjk / words, chapter_id, index, words, cjk))

    ratios.sort()
    print(f"paragraph pairs: {len(ratios)}")
    print()
    print("ratio = CJK characters per English word")
    for label, value in (
        ("minimum", ratios[0][0]),
        ("5th pct", ratios[len(ratios) // 20][0]),
        ("25th pct", ratios[len(ratios) // 4][0]),
        ("median", ratios[len(ratios) // 2][0]),
        ("75th pct", ratios[3 * len(ratios) // 4][0]),
        ("95th pct", ratios[19 * len(ratios) // 20][0]),
        ("maximum", ratios[-1][0]),
    ):
        print(f"  {label:<10} {value:.2f}")

    for threshold in (0.6, 0.8, 1.0, 1.2):
        flagged = [row for row in ratios if row[0] < threshold]
        chapters_affected = len({row[1] for row in flagged})
        print(
            f"  ratio < {threshold:.1f}: {len(flagged):>4} paragraphs "
            f"in {chapters_affected:>3} chapters"
        )

    print()
    print("20 thinnest paragraphs:")
    for ratio, chapter_id, index, words, cjk in ratios[:20]:
        print(
            f"  {chapter_id} p{index}: ratio={ratio:.2f} en_words={words:>3} cjk={cjk:>3}"
        )
    print()
    print("10 densest paragraphs (reference for a faithful rendering):")
    for ratio, chapter_id, index, words, cjk in ratios[-10:]:
        print(
            f"  {chapter_id} p{index}: ratio={ratio:.2f} en_words={words:>3} cjk={cjk:>3}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
