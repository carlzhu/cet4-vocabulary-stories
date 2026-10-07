"""Contract tests for approved curriculum chapters, their schema, and models."""

from __future__ import annotations

from copy import deepcopy
from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Any

import pytest
from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "source"))
SAMPLE_PATH = PROJECT_ROOT / "drafts" / "sample_chapters.json"
SCHEMA_PATH = (
    PROJECT_ROOT / "source" / "cet4_story" / "schemas" / "chapter.schema.json"
)
Chapter = import_module("cet4_story.models").Chapter

APPROVED_SAMPLE_METADATA = (
    ("CH001", "New Ground: A Signal", "新的起点：一个信号", "大学生活与个人成长"),
    (
        "CH050",
        "The First Real Deadline: What the Numbers Hide",
        "第一个真实期限：数字隐藏了什么",
        "求职、职场与职业发展",
    ),
    (
        "CH090",
        "What the System Remembers: Pressure Builds",
        "系统记住了什么：压力上升",
        "科学、技术与互联网",
    ),
)


def _approved_sample_snapshot(
    article_id: str, english_title: str, chinese_title: str, theme: str
) -> dict[str, Any]:
    """Build the preserved sample shape when protected source data is not staged."""

    return {
        "article_id": article_id,
        "english_title": english_title,
        "chinese_title": chinese_title,
        "theme": theme,
        "english_paragraphs": [
            f"Approved English paragraph {number} for {article_id}."
            for number in range(1, 5)
        ],
        "chinese_paragraphs": [
            f"{article_id} 的已批准中文段落 {number}。" for number in range(1, 5)
        ],
        "exercises": [
            {
                "id": f"{article_id}-Q{number}",
                "type": "context",
                "prompt": f"Approved question {number} for {article_id}?",
                "options": ["alpha", "beta", "gamma", "delta"],
            }
            for number in range(1, 6)
        ],
        "answers": [
            {
                "id": f"{article_id}-Q{number}",
                "answer": "alpha",
                "explanation": f"Approved explanation {number} for {article_id}.",
            }
            for number in range(1, 6)
        ],
    }


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    loaded = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(loaded)
    return loaded


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def approved_chapters() -> list[dict[str, Any]]:
    if SAMPLE_PATH.is_file():
        document = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        assert document["schema_version"] == 1
        chapters = document["chapters"]
    else:
        chapters = [_approved_sample_snapshot(*metadata) for metadata in APPROVED_SAMPLE_METADATA]

    assert [chapter["article_id"] for chapter in chapters] == [
        "CH001",
        "CH050",
        "CH090",
    ]
    return chapters


def assert_schema_and_model_reject(
    chapter: dict[str, Any], validator: Draft202012Validator
) -> None:
    assert list(validator.iter_errors(chapter)), "JSON Schema unexpectedly accepted data"
    with pytest.raises((TypeError, ValueError)):
        Chapter.from_dict(chapter)


def test_approved_samples_validate_and_round_trip(
    approved_chapters: list[dict[str, Any]], validator: Draft202012Validator
) -> None:
    for chapter_data in approved_chapters:
        validator.validate(chapter_data)
        chapter = Chapter.from_dict(chapter_data)
        assert chapter.to_dict() == chapter_data
        assert len(chapter.paragraphs) == len(chapter_data["english_paragraphs"])
        assert [paragraph.index for paragraph in chapter.paragraphs] == list(
            range(1, len(chapter.paragraphs) + 1)
        )


@pytest.mark.parametrize(
    ("collection", "bad_id"),
    [
        (None, "CH01"),
        ("exercises", "CH001-Q0"),
        ("answers", "CH001-Q6"),
    ],
)
def test_malformed_ids_are_rejected(
    approved_chapters: list[dict[str, Any]],
    validator: Draft202012Validator,
    collection: str | None,
    bad_id: str,
) -> None:
    chapter = deepcopy(approved_chapters[0])
    if collection is None:
        chapter["article_id"] = bad_id
    else:
        chapter[collection][0]["id"] = bad_id

    assert_schema_and_model_reject(chapter, validator)


def test_paragraph_misalignment_is_rejected(
    approved_chapters: list[dict[str, Any]], validator: Draft202012Validator
) -> None:
    chapter = deepcopy(approved_chapters[0])
    chapter["chinese_paragraphs"].pop()

    assert_schema_and_model_reject(chapter, validator)


def test_answers_embedded_in_exercises_are_rejected(
    approved_chapters: list[dict[str, Any]], validator: Draft202012Validator
) -> None:
    chapter = deepcopy(approved_chapters[0])
    chapter["exercises"][0]["answer"] = chapter["answers"][0]["answer"]

    assert_schema_and_model_reject(chapter, validator)


@pytest.mark.parametrize("exercise_count", [4, 6])
def test_wrong_exercise_count_is_rejected(
    approved_chapters: list[dict[str, Any]],
    validator: Draft202012Validator,
    exercise_count: int,
) -> None:
    chapter = deepcopy(approved_chapters[0])
    if exercise_count == 4:
        chapter["exercises"].pop()
    else:
        chapter["exercises"].append(deepcopy(chapter["exercises"][-1]))

    assert_schema_and_model_reject(chapter, validator)
