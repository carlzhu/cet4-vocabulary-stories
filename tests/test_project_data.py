"""Integration tests that run the ported pipeline against the real project data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cet4_story.project_data import (
    PROVENANCE_PATH,
    load_project,
    verify_invariants,
    write_provenance,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "drafts" / "sample_chapters.json"
SAMPLE_IDS = ("CH001", "CH050", "CH090")


@pytest.fixture(scope="module")
def project():
    if not (PROJECT_ROOT / PROVENANCE_PATH).is_file():
        write_provenance(PROJECT_ROOT)
    return load_project(PROJECT_ROOT)


def test_protected_source_invariants(project) -> None:
    summary = verify_invariants(project)

    assert summary["vocabulary_records"] == 6127
    assert summary["chapters"] == 137
    assert summary["review_events"] == 36762
    assert summary["allocated_targets"] == 6127
    assert summary["metadata_matched"] == 6127
    assert project.chapter_ids[0] == "CH001"
    assert project.chapter_ids[-1] == "CH137"


def test_metadata_enrichment_carries_inflections(project) -> None:
    ability = next(
        row for row in project.vocabulary_by_id.values() if row["lemma"] == "ability"
    )
    assert ability["ecdict_exchange"]
    assert ability["translation"]

    with_inflections = sum(
        1 for row in project.vocabulary_by_id.values() if row.get("ecdict_exchange")
    )
    assert with_inflections > 0


def test_approved_samples_pass_the_deterministic_validator(project) -> None:
    document = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    chapters = {chapter["article_id"]: chapter for chapter in document["chapters"]}
    assert set(chapters) == set(SAMPLE_IDS)

    validator = project.validator()
    for chapter_id in SAMPLE_IDS:
        report = validator.check(chapters[chapter_id])
        assert report.errors == (), f"{chapter_id}: {report.errors}"
        assert report.coverage_occurrences
        unverified = [
            occurrence.vocabulary_id
            for occurrence in report.coverage_occurrences
            if occurrence.status != "verified"
        ]
        assert unverified == [], f"{chapter_id} unverified targets: {unverified}"


def test_allocation_matches_the_plan_for_a_sample_chapter(project) -> None:
    planned = project.source.new_vocabulary_ids_by_chapter["CH001"]
    assert len(planned) == 45

    document = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    chapter = next(item for item in document["chapters"] if item["article_id"] == "CH001")
    report = project.validator().check(chapter)
    reported = [occurrence.vocabulary_id for occurrence in report.coverage_occurrences]
    assert reported[: len(planned)] == list(planned)
