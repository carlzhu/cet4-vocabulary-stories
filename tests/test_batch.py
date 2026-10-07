"""Tests for batch storage, checkpointing, and continuity validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cet4_story.batch import (
    APPROVED_SAMPLE_CHAPTERS,
    BatchError,
    commit_batch,
    completed_chapter_ids,
    continuity_path,
    load_batch,
    load_checkpoint,
    next_batch_chapter_ids,
    rebuild_checkpoint,
    record_boundary,
    save_checkpoint,
    validate_batch,
    write_batch,
)
from cet4_story.continuity import check_boundary, load_continuity, parse_cast
from cet4_story.models import Chapter, Checkpoint, ContinuityState
from cet4_story.project_data import PROVENANCE_PATH, load_project, write_provenance

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "drafts" / "sample_chapters.json"


@pytest.fixture(scope="module")
def project():
    if not (PROJECT_ROOT / PROVENANCE_PATH).is_file():
        write_provenance(PROJECT_ROOT)
    return load_project(PROJECT_ROOT)


@pytest.fixture(scope="module")
def sample_chapters() -> tuple[Chapter, ...]:
    document = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    return tuple(Chapter.from_dict(entry) for entry in document["chapters"])


def _state(chapter_id: str, **overrides) -> ContinuityState:
    payload = {
        "chapter_id": chapter_id,
        "last_event": "The team removed the copied field.",
        "unresolved_consequence": "The sequence still needs review.",
        "character_locations": {"Lin Wei": "control room"},
        "character_roles": {"Lin Wei": "student engineer"},
        "open_commitments": ("rebuild the approval data",),
        "open_conflicts": ("schedule pressure",),
        "first_required_event_next_chapter": "Independent approval is requested.",
        "established_facts": ("the airport project is under test",),
    }
    payload.update(overrides)
    return ContinuityState(**payload)


def test_cast_is_parsed_from_the_character_guide(project) -> None:
    cast = parse_cast(project.source.character_guide)

    assert "Lin Wei" in cast
    assert "Maya Chen" in cast
    assert "Daniel Brooks" in cast
    assert len(cast) >= 6


def test_next_batch_skips_the_approved_samples() -> None:
    first = next_batch_chapter_ids(APPROVED_SAMPLE_CHAPTERS)
    assert first == tuple(f"CH{number:03d}" for number in range(2, 10))

    with_ch049 = next_batch_chapter_ids(
        [*APPROVED_SAMPLE_CHAPTERS, *(f"CH{number:03d}" for number in range(2, 50))]
    )
    assert with_ch049 == ("CH051", "CH052", "CH053", "CH054", "CH055", "CH056", "CH057", "CH058")

    tail = next_batch_chapter_ids([f"CH{number:03d}" for number in range(1, 131)])
    assert tail == ("CH131", "CH132", "CH133", "CH134", "CH135", "CH136", "CH137")


def test_batch_round_trip_and_no_silent_overwrite(
    tmp_path: Path, sample_chapters: tuple[Chapter, ...]
) -> None:
    batch = write_batch(tmp_path, sample_chapters)
    assert batch.chapter_ids == ("CH001", "CH050", "CH090")
    assert batch.sha256

    reloaded = load_batch(batch.path)
    assert reloaded.chapter_ids == batch.chapter_ids
    assert reloaded.sha256 == batch.sha256
    assert [chapter.to_dict() for chapter in reloaded.chapters] == [
        chapter.to_dict() for chapter in sample_chapters
    ]

    with pytest.raises(BatchError):
        write_batch(tmp_path, sample_chapters)


def test_checkpoint_round_trip_and_rebuild(
    tmp_path: Path, sample_chapters: tuple[Chapter, ...]
) -> None:
    empty = load_checkpoint(tmp_path)
    assert empty.version == 1
    assert empty.next_chapter_id == "CH001"

    batch = write_batch(tmp_path, sample_chapters)
    checkpoint = Checkpoint(
        completed_chapter_ids=batch.chapter_ids,
        batch_hashes={batch.batch_id: batch.sha256},
        validation_counts={"batches": 1},
        next_chapter_id="CH002",
    )
    save_checkpoint(tmp_path, checkpoint)
    assert load_checkpoint(tmp_path) == checkpoint

    rebuilt = rebuild_checkpoint(tmp_path)
    assert rebuilt.batch_hashes == {batch.batch_id: batch.sha256}
    assert set(rebuilt.completed_chapter_ids) == set(APPROVED_SAMPLE_CHAPTERS)
    assert rebuilt.next_chapter_id == "CH002"
    assert completed_chapter_ids(tmp_path) == APPROVED_SAMPLE_CHAPTERS


def test_validate_batch_on_the_real_samples(project, sample_chapters: tuple[Chapter, ...]) -> None:
    outcome = validate_batch(sample_chapters, project, require_continuity=False)

    assert outcome.result.schema_valid
    assert outcome.result.plan_valid
    assert outcome.result.coverage_valid
    assert outcome.result.errors == ()
    assert outcome.verified_new == 135
    assert outcome.verified_review == 36
    assert outcome.needs_revision == 0


def test_commit_batch_records_the_checkpoint(
    tmp_path: Path, project, sample_chapters: tuple[Chapter, ...]
) -> None:
    batch = write_batch(tmp_path, sample_chapters)
    outcome = validate_batch(sample_chapters, project, require_continuity=False)

    checkpoint = commit_batch(tmp_path, batch, outcome)
    assert checkpoint.batch_hashes[batch.batch_id] == batch.sha256
    assert checkpoint.next_chapter_id == "CH002"
    assert set(APPROVED_SAMPLE_CHAPTERS).issubset(checkpoint.completed_chapter_ids)

    stored = load_checkpoint(tmp_path)
    assert stored == checkpoint


def test_boundary_rejects_dropped_facts_unknown_cast_and_silent_resolution(project) -> None:
    cast = parse_cast(project.source.character_guide)
    previous = _state("CH002")
    current = _state(
        "CH003",
        established_facts=("the airport project is under test", "the delay is documented"),
        character_locations={"Lin Wei": "control room", "Nobody At All": "the moon"},
    )

    errors = check_boundary(previous, current, cast=cast, expected_first_chapter="CH003")
    assert any("unknown character in location" in error for error in errors)
    assert not any("established facts were dropped" in error for error in errors)

    dropped = _state("CH003")
    errors = check_boundary(previous, dropped, cast=cast, expected_first_chapter="CH003")
    assert not any("established facts were dropped" in error for error in errors)

    silent = _state(
        "CH003",
        open_commitments=(),
        open_conflicts=(),
        last_event="The team closed the runway and went home.",
    )
    errors = check_boundary(previous, silent, cast=cast, expected_first_chapter="CH003")
    assert any("open commitment" in error for error in errors)
    assert any("open conflict" in error for error in errors)

    erased = _state("CH003", established_facts=("something else entirely",))
    errors = check_boundary(previous, erased, cast=cast, expected_first_chapter="CH003")
    assert any("established facts were dropped" in error for error in errors)


def test_boundary_records_are_logged_in_chapter_order(tmp_path: Path) -> None:
    record_boundary(tmp_path, _state("CH002"))
    record_boundary(tmp_path, _state("CH003"), previous_state=_state("CH002"))

    states = load_continuity(continuity_path(tmp_path))
    assert list(states) == ["CH002", "CH003"]

    with pytest.raises(BatchError):
        record_boundary(tmp_path, _state("CH005"), previous_state=_state("CH004"))
