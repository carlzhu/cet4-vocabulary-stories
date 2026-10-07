"""Guard against .notdef boxes: every drawn character must exist in its font.

This is the check whose absence let 4,540 of 6,127 phonetic rows print as boxes.
Counting U+FFFD in extracted text cannot catch it, because the PDF stores the
correct character; only the font lacks the glyph. Here the check runs on the
inputs - the strings that will be drawn and the font that will draw them.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from cet4_story.pdf_builder import select_chapters
from cet4_story.project_data import load_project

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ARIAL = Path(r"C:\WINDOWS\Fonts\arial.ttf")
SIMHEI = Path(r"C:\WINDOWS\Fonts\simhei.ttf")

INVISIBLE_ALLOWED = {"\n", "\r", "\t", "\u00a0"}


def _cmap(path: Path) -> set[int]:
    with TTFont(str(path), fontNumber=0, lazy=True) as font:
        covered: set[int] = set()
        for table in font["cmap"].tables:
            covered.update(table.cmap.keys())
        return covered


@pytest.fixture(scope="module")
def project():
    return load_project(PROJECT_ROOT)


@pytest.mark.skipif(not ARIAL.is_file(), reason="Arial not installed")
def test_latin_and_phonetic_text_is_drawable_in_arial(project) -> None:
    used: Counter[str] = Counter()
    for row in project.vocabulary_by_id.values():
        used.update(row.get("lemma") or "")
        used.update(row.get("phonetic") or "")

    covered = _cmap(ARIAL)
    missing = {
        character: count
        for character, count in used.items()
        if character not in INVISIBLE_ALLOWED and ord(character) not in covered
    }
    assert missing == {}, f"Arial cannot draw: {sorted(missing)}"

    # The IPA inventory is the reason Arial is required here.
    ipa = {character for character in used if ord(character) > 127}
    assert ipa, "expected non-ASCII phonetics characters in the target set"


@pytest.mark.skipif(not SIMHEI.is_file(), reason="SimHei not installed")
def test_chinese_and_english_story_text_is_drawable_in_simhei(project) -> None:
    used: Counter[str] = Counter()
    for row in project.vocabulary_by_id.values():
        for field in ("chinese_meaning", "ecdict_examples", "definition", "part_of_speech"):
            used.update(row.get(field) or "")
    for chapter in select_chapters(PROJECT_ROOT, "all"):
        used.update(chapter.english_title)
        used.update(chapter.chinese_title)
        used.update(chapter.theme)
        for paragraph in chapter.english_paragraphs:
            used.update(paragraph)
        for paragraph in chapter.chinese_paragraphs:
            used.update(paragraph)
        for exercise in chapter.exercises:
            used.update(exercise.prompt)
            used.update(" ".join(exercise.options))
        for answer in chapter.answers:
            used.update(answer.answer)
            used.update(answer.explanation)

    covered = _cmap(SIMHEI)
    missing = {
        character: count
        for character, count in used.items()
        if character not in INVISIBLE_ALLOWED and ord(character) not in covered
    }
    assert missing == {}, f"SimHei cannot draw: {sorted(missing)}"


def test_no_zero_width_or_control_characters_in_generated_text(project) -> None:
    """Stray invisible characters print as boxes, so reject them outright."""

    forbidden = {"\u200b", "\u200c", "\u200d", "\ufeff", "\x00"}
    offenders: list[str] = []
    for chapter in select_chapters(PROJECT_ROOT, "all"):
        blobs = {
            "english_paragraphs": " ".join(chapter.english_paragraphs),
            "chinese_paragraphs": " ".join(chapter.chinese_paragraphs),
            "titles": chapter.english_title + chapter.chinese_title,
        }
        for exercise in chapter.exercises:
            blobs[f"exercise {exercise.id}"] = exercise.prompt + " ".join(exercise.options)
        for answer in chapter.answers:
            blobs[f"answer {answer.id}"] = answer.answer + " " + answer.explanation
        for name, text in blobs.items():
            for character in forbidden:
                if character in text:
                    offenders.append(f"{chapter.article_id} {name}: U+{ord(character):04X}")

    assert offenders == [], f"invisible characters found: {offenders}"
