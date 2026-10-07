"""Contract tests for deterministic chapter validation."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pathlib import Path
import sys
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "source"))
validation = import_module("cet4_story.validation")

ChapterValidationError = validation.ChapterValidationError
validate_chapter = validation.validate_chapter

APPROVED_SAMPLE_METADATA = (
    ("CH001", "New Ground: A Signal", "新的起点：一个信号", "大学生活与个人成长", "V0001", "signal"),
    (
        "CH050",
        "The First Real Deadline: What the Numbers Hide",
        "第一个真实期限：数字隐藏了什么",
        "求职、职场与职业发展",
        "V0050",
        "deadline",
    ),
    (
        "CH090",
        "What the System Remembers: Pressure Builds",
        "系统记住了什么：压力上升",
        "科学、技术与互联网",
        "V0090",
        "system",
    ),
)


def _story_paragraph(target: str, paragraph_number: int) -> str:
    """Return exactly 90 English words containing one target occurrence."""

    words = [
        target,
        "appears",
        "while",
        "the",
        "students",
        "carefully",
        "continue",
        "their",
        "shared",
        "journey",
    ]
    words.extend(["forward"] * 79)
    words.append(f"chapter{paragraph_number}")
    assert len(words) == 90
    return " ".join(words) + "."


def _approved_chapter(
    article_id: str,
    english_title: str,
    chinese_title: str,
    theme: str,
    target: str,
) -> dict[str, Any]:
    return {
        "article_id": article_id,
        "english_title": english_title,
        "chinese_title": chinese_title,
        "theme": theme,
        "english_paragraphs": [
            _story_paragraph(target, number) for number in range(1, 5)
        ],
        "chinese_paragraphs": [
            f"第 {number} 段与对应英文段落对齐。" for number in range(1, 5)
        ],
        "exercises": [
            {
                "id": f"{article_id}-Q{number}",
                "type": "context",
                "prompt": f"What develops in paragraph {number}?",
                "options": ["careful progress", "a retreat", "a delay", "silence"],
            }
            for number in range(1, 6)
        ],
        "answers": [
            {
                "id": f"{article_id}-Q{number}",
                "answer": "careful progress",
                "explanation": "The story describes steady collaborative progress.",
            }
            for number in range(1, 6)
        ],
    }


def _plan(
    article_id: str,
    english_title: str,
    theme: str,
    vocabulary_id: str,
) -> dict[str, str]:
    return {
        "chapter_id": article_id,
        "title": english_title,
        "theme": theme,
        "plot_summary": "The characters make measurable progress together.",
        "new_vocabulary_ids": f'["{vocabulary_id}"]',
        "review_vocabulary_ids": "[]",
    }


def _vocabulary(vocabulary_id: str, target: str) -> dict[str, dict[str, str]]:
    return {
        vocabulary_id: {
            "vocabulary_id": vocabulary_id,
            "word": target,
            "exchange": "",
        }
    }


@pytest.fixture(params=APPROVED_SAMPLE_METADATA, ids=("CH001", "CH050", "CH090"))
def approved_case(
    request: pytest.FixtureRequest,
) -> tuple[dict[str, Any], dict[str, str], dict[str, dict[str, str]]]:
    article_id, english_title, chinese_title, theme, vocabulary_id, target = (
        request.param
    )
    return (
        _approved_chapter(
            article_id, english_title, chinese_title, theme, target
        ),
        _plan(article_id, english_title, theme, vocabulary_id),
        _vocabulary(vocabulary_id, target),
    )


def _assert_invalid(
    chapter: dict[str, Any],
    plan: dict[str, str],
    vocabulary: dict[str, dict[str, str]],
    expected_message: str,
) -> ChapterValidationError:
    with pytest.raises(ChapterValidationError) as caught:
        validate_chapter(chapter, plan, vocabulary)
    assert expected_message in str(caught.value)
    assert not caught.value.report.is_valid
    return caught.value


def test_approved_samples_pass_deterministic_validation(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = approved_case

    report = validate_chapter(chapter, plan, vocabulary)

    assert report.is_valid
    assert report.word_count == 360
    assert report.paragraph_count == 4
    assert report.exercise_count == 5
    assert report.answer_count == 5
    assert len(report.coverage_occurrences) == 1
    assert report.coverage_occurrences[0].status == "verified"


def test_missing_planned_word_is_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    target = next(iter(vocabulary.values()))["word"]
    chapter["english_paragraphs"] = [
        paragraph.replace(target, "clue")
        for paragraph in chapter["english_paragraphs"]
    ]

    error = _assert_invalid(
        chapter, plan, vocabulary, "is not verified in English story text"
    )

    assert error.report.coverage_occurrences[0].occurrence_count == 0
    assert error.report.coverage_occurrences[0].status == "needs_revision"


@pytest.mark.parametrize(
    ("field", "replacement", "expected_message"),
    [
        ("english_title", "An Unapproved Title", "english_title does not match"),
        ("theme", "An Unapproved Theme", "theme does not match"),
    ],
)
def test_wrong_protected_metadata_is_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
    field: str,
    replacement: str,
    expected_message: str,
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    chapter[field] = replacement

    _assert_invalid(chapter, plan, vocabulary, expected_message)


def test_unaligned_translations_are_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    chapter["chinese_paragraphs"].pop()

    _assert_invalid(
        chapter,
        plan,
        vocabulary,
        "English and Chinese paragraph counts must match",
    )


def test_malformed_questions_are_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    chapter["exercises"][0]["id"] = f"{chapter['article_id']}-Q0"

    _assert_invalid(chapter, plan, vocabulary, "invalid exercise id")


def test_answers_inside_exercise_text_are_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    leaked_answer = chapter["answers"][0]["answer"]
    chapter["exercises"][0]["prompt"] = (
        f"The correct answer is {leaked_answer}. Why?"
    )

    _assert_invalid(
        chapter,
        plan,
        vocabulary,
        "prompt contains its matching answer",
    )


def test_out_of_scope_only_vocabulary_matches_are_rejected(
    approved_case: tuple[
        dict[str, Any], dict[str, str], dict[str, dict[str, str]]
    ],
) -> None:
    chapter, plan, vocabulary = deepcopy(approved_case)
    target = next(iter(vocabulary.values()))["word"]
    chapter["english_paragraphs"] = [
        paragraph.replace(target, "clue")
        for paragraph in chapter["english_paragraphs"]
    ]
    chapter["english_title"] = target
    plan["title"] = target
    chapter["exercises"][0]["prompt"] = f"Where does {target} appear?"
    chapter["answers"][0]["explanation"] = (
        f"The out-of-scope explanation mentions {target}."
    )

    error = _assert_invalid(
        chapter, plan, vocabulary, "is not verified in English story text"
    )

    occurrence = error.report.coverage_occurrences[0]
    assert occurrence.occurrence_count == 0
    assert occurrence.context_sentence is None
