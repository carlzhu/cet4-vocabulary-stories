from __future__ import annotations

from cet4_story.planner import (
    ARTICLE_COUNT,
    CAPACITIES,
    REVIEW_OFFSETS,
    allocate,
    build_reviews,
)


def _rows() -> list[dict[str, str]]:
    return [{
        "vocabulary_id": f"cet4-{index:012d}",
        "lemma": f"word{index:04d}",
        "english_definition": "general vocabulary",
        "chinese_meaning": "词汇",
        "ecdict_bnc_frequency": str(index + 1),
        "ecdict_contemporary_frequency": str(index + 2),
    } for index in range(6127)]


def test_capacity_exactly_covers_baseline() -> None:
    assert ARTICLE_COUNT == 137
    assert len(CAPACITIES) == ARTICLE_COUNT
    assert sum(CAPACITIES) == 6127
    assert CAPACITIES.count(45) == 99
    assert CAPACITIES.count(44) == 38


def test_allocation_and_review_schedule_reconcile() -> None:
    rows = _rows()
    mapping, chapters = allocate(rows)
    schedule, story_reviews = build_reviews(rows, mapping)
    assert len(mapping) == 6127
    assert [len(chapter) for chapter in chapters] == CAPACITIES
    assert len(schedule) == 6127 * len(REVIEW_OFFSETS)
    assert all(len(ids) <= 18 for ids in story_reviews.values())
    assert all(row["mastery_status"] == "unassessed" for row in schedule)
