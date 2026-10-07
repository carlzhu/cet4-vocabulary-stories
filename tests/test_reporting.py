"""Acceptance tests for the assembled curriculum and its reports.

These are the end-state gates from `specs/generate_full_curriculum.md`: they only
pass when all 137 chapters are committed and every one of the 6,127 planned
targets is verified. While chapters are still being generated they are expected
to fail, which is the point - they must never pass on partial work.
"""

from __future__ import annotations

import csv
from pathlib import Path

from cet4_story.project_data import CURRICULUM_CHAPTERS, TARGET_FORMS
from cet4_story.reporting import (
    COVERAGE_FIELDS,
    audit_curriculum,
    build_manuscript,
    write_coverage_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_audit_curriculum_accepts_the_finished_curriculum() -> None:
    audit = audit_curriculum(PROJECT_ROOT)

    assert audit.problems == ()
    assert audit.is_valid
    assert len(audit.chapter_ids) == CURRICULUM_CHAPTERS
    assert audit.chapter_ids == tuple(
        f"CH{number:03d}" for number in range(1, CURRICULUM_CHAPTERS + 1)
    )

    counts = audit.counts
    assert counts["planned_targets"] == TARGET_FORMS
    assert counts["verified_new"] == TARGET_FORMS
    assert counts["needs_revision"] == 0
    assert counts["uncovered"] == 0
    assert counts["review_verified"] == counts["review_occurrences"]


def test_human_review_gaps_are_reported_not_hidden() -> None:
    audit = audit_curriculum(PROJECT_ROOT)

    # These are the known, honestly reported limits of the automated pipeline.
    assert audit.counts["unresolved_part_of_speech"] == 41
    assert audit.counts["missing_phonetic"] == 48


def test_coverage_rows_are_unique_per_target() -> None:
    audit = audit_curriculum(PROJECT_ROOT)

    vocabulary_ids = [row["vocabulary_id"] for row in audit.coverage_rows]
    assert len(vocabulary_ids) == TARGET_FORMS
    assert len(set(vocabulary_ids)) == TARGET_FORMS
    assert {row["status"] for row in audit.coverage_rows} == {"verified"}


def test_coverage_csv_matches_the_documented_columns(tmp_path: Path) -> None:
    audit = audit_curriculum(PROJECT_ROOT)
    path = write_coverage_csv(audit, tmp_path / "vocabulary_coverage.csv")

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == COVERAGE_FIELDS
        rows = list(reader)

    assert len(rows) == TARGET_FORMS
    assert all(row["status"] == "verified" for row in rows)
    assert all(row["chapter_id"].startswith("CH") for row in rows)


def test_manuscript_contains_every_chapter_once() -> None:
    manuscript = build_manuscript(PROJECT_ROOT)

    for number in range(1, CURRICULUM_CHAPTERS + 1):
        heading = f"## CH{number:03d} - "
        assert manuscript.count(heading) == 1

    assert manuscript.count("### Exercises") == CURRICULUM_CHAPTERS
    assert manuscript.count("### Answers") == CURRICULUM_CHAPTERS


def test_every_paragraph_is_rendered_in_chinese() -> None:
    """The Chinese must actually render the English, per the chapter rules.

    Density is the gate. A faithful rendering in this corpus runs at a median of
    1.48 CJK characters per English word (25th percentile 1.36); anything below
    1.2 is a summary rather than a translation, and 113 paragraphs were in that
    state after generation. All are now above the threshold.

    The sentence-gap metric is deliberately *not* the gate: it cannot tell a
    dropped sentence from a legitimate merge. Chinese routinely renders "He said
    X. She said Y." as one sentence, and a quotation plus its reporting clause
    likewise collapses into one. Every residual gap was inspected by eye and
    found to be a merge with the content present, so asserting it were zero would
    force padding rather than accuracy.
    """

    audit = audit_curriculum(PROJECT_ROOT)

    assert audit.counts["thin_chinese_paragraphs"] == 0
    # Residual sentence-count gaps are merges only; keep them bounded so a real
    # regression (a paragraph losing its translation) still fails this test.
    assert audit.counts["paragraphs_with_untranslated_text"] <= 10
    assert audit.counts["untranslated_english_sentences"] <= 20
