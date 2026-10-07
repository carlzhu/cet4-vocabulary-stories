"""Fail the build when a character would print as a .notdef box.

Why this is an input-side check
-------------------------------

The obvious approach - walk the PDF's text spans and ask each span's font whether
it has the glyph - does not work here. The embedded subsets are CID fonts with
unreliable ToUnicode entries, so ``page.get_text("rawdict")`` returns ``\\x00`` or
a guessed character for many spans. Trying it produced 203,870 "violations"
including ``的``, ``—`` and ``“``, all of which render perfectly. A checker that
cries wolf on 12% of the document is worse than none.

So this check is deterministic and runs on the inputs instead: for every string
that is about to be drawn, and the font that will draw it, confirm the font file's
cmap has a glyph for every character. The rendered result was then confirmed by
comparing page pixels before and after the fix.

This is the check whose absence let 4,540 of 6,127 phonetic rows print as boxes:
the phonetic column was styled with SimHei, which cannot draw 15 of the 19
non-ASCII phonetics characters.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from fontTools.ttLib import TTFont  # noqa: E402

from cet4_story.pdf_builder import select_chapters  # noqa: E402
from cet4_story.project_data import load_project  # noqa: E402

# Fonts the PDF registers, and the text that is drawn with each. Latin/IPA runs
# are tagged with CETEnglish in the table; everything else uses CETChinese.
FONTS = {
    "CETEnglish": Path(r"C:\WINDOWS\Fonts\arial.ttf"),
    "CETEnglishBold": Path(r"C:\WINDOWS\Fonts\arialbd.ttf"),
    "CETChinese": Path(r"C:\WINDOWS\Fonts\simhei.ttf"),
}


def cmap_for(path: Path) -> set[int]:
    with TTFont(str(path), fontNumber=0, lazy=True) as font:
        covered: set[int] = set()
        for table in font["cmap"].tables:
            covered.update(table.cmap.keys())
        return covered


def main() -> int:
    project = load_project(ROOT)
    chapters = select_chapters(ROOT, "all")

    # Text drawn with the Latin font: lemmas and phonetic transcriptions.
    latin_chars: Counter[str] = Counter()
    for row in project.vocabulary_by_id.values():
        latin_chars.update(row.get("lemma") or "")
        latin_chars.update(row.get("phonetic") or "")
    # Text drawn with the CJK font: meanings, examples, headings, translations.
    cjk_chars: Counter[str] = Counter()
    for row in project.vocabulary_by_id.values():
        cjk_chars.update(row.get("chinese_meaning") or "")
        cjk_chars.update(row.get("ecdict_examples") or "")
        cjk_chars.update(row.get("definition") or "")
        cjk_chars.update(row.get("part_of_speech") or "")
    for chapter in chapters:
        cjk_chars.update(chapter.english_title)
        cjk_chars.update(chapter.chinese_title)
        cjk_chars.update(chapter.theme)
        for paragraph in chapter.english_paragraphs:
            cjk_chars.update(paragraph)
        for paragraph in chapter.chinese_paragraphs:
            cjk_chars.update(paragraph)
        for exercise in chapter.exercises:
            cjk_chars.update(exercise.prompt)
            cjk_chars.update(" ".join(exercise.options))
        for answer in chapter.answers:
            cjk_chars.update(answer.answer)
            cjk_chars.update(answer.explanation)

    checks = {
        "CETEnglish": latin_chars,
        "CETChinese": cjk_chars,
    }

    failed = False
    for font_name, used in checks.items():
        path = FONTS[font_name]
        if not path.is_file():
            print(f"{font_name}: font file missing at {path}")
            failed = True
            continue
        covered = cmap_for(path)
        missing = {
            character: count
            for character, count in used.items()
            if character not in {"\n", "\r", "\t", "\u00a0"} and ord(character) not in covered
        }
        status = "PASS" if not missing else "FAIL"
        print(
            f"{font_name:<16} ({path.name}) distinct_chars={len(used):>5} "
            f"undrawable={len(missing):>3} -> {status}"
        )
        for character, count in sorted(missing.items(), key=lambda kv: -kv[1]):
            print(f"    U+{ord(character):04X} {character!r}: {count} occurrences")
        if missing:
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
