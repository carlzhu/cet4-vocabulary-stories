"""Recoverable batch storage, checkpointing, and batch-level validation.

Batches are JSON documents shaped like ``drafts/sample_chapters.json`` so the
approved samples and generated chapters share one format.  A checkpoint is
written only after a batch validates completely, and a batch already on disk is
never overwritten by a later run, so a failing later batch can never discard
earlier validated work.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cet4_story.continuity import (
    CONTINUITY_FILENAME,
    check_boundary,
    load_continuity,
    parse_cast,
    save_continuity,
    state_from_dict,
    state_to_dict,
)
from cet4_story.models import (
    BatchValidationResult,
    Chapter,
    Checkpoint,
    ContinuityState,
    CoverageOccurrence,
)
from cet4_story.project_data import CURRICULUM_CHAPTERS, ProjectData
from cet4_story.validation import ChapterValidationError, ChapterValidationReport

BATCH_DIR = Path("drafts") / "batches"
CHECKPOINT_FILENAME = "checkpoint.json"
BATCH_SCHEMA_VERSION = 1
DEFAULT_BATCH_SIZE = 8

APPROVED_SAMPLE_CHAPTERS = ("CH001", "CH050", "CH090")

# The ported validator reports uncovered targets with this fixed phrase; batch
# validation uses it only to separate coverage errors from structural ones.
COVERAGE_ERROR_PHRASE = "is not verified in English story text"


class BatchError(ValueError):
    """A batch file, checkpoint, or batch validation contract was violated."""


@dataclass(frozen=True, slots=True)
class BatchFile:
    """One validated batch document on disk."""

    path: Path
    batch_id: str
    chapter_ids: tuple[str, ...]
    sha256: str
    chapters: tuple[Chapter, ...]
    continuity: ContinuityState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "path": str(self.path),
            "chapter_ids": list(self.chapter_ids),
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class BatchValidation:
    """Complete evidence for one batch validation run."""

    result: BatchValidationResult
    reports: tuple[ChapterValidationReport, ...]
    occurrences: tuple[CoverageOccurrence, ...]

    @property
    def verified_new(self) -> int:
        return sum(
            1 for item in self.occurrences if item.kind == "new" and item.status == "verified"
        )

    @property
    def verified_review(self) -> int:
        return sum(
            1
            for item in self.occurrences
            if item.kind == "review" and item.status == "verified"
        )

    @property
    def needs_revision(self) -> int:
        return sum(1 for item in self.occurrences if item.status == "needs_revision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.result.batch_id,
            "chapter_ids": list(self.result.chapter_ids),
            "schema_valid": self.result.schema_valid,
            "plan_valid": self.result.plan_valid,
            "coverage_valid": self.result.coverage_valid,
            "continuity_valid": self.result.continuity_valid,
            "validation_counts": dict(self.result.validation_counts),
            "errors": list(self.result.errors),
            "chapters": [
                {
                    "chapter_id": report.chapter_id,
                    "word_count": report.word_count,
                    "paragraph_count": report.paragraph_count,
                    "exercise_count": report.exercise_count,
                    "answer_count": report.answer_count,
                    "errors": list(report.errors),
                    "verified_new": sum(
                        1
                        for item in report.coverage_occurrences
                        if item.kind == "new" and item.status == "verified"
                    ),
                    "verified_review": sum(
                        1
                        for item in report.coverage_occurrences
                        if item.kind == "review" and item.status == "verified"
                    ),
                }
                for report in self.reports
            ],
        }


def batches_dir(root: str | Path) -> Path:
    return Path(root).resolve() / BATCH_DIR


def batch_id_for(chapter_ids: Sequence[str]) -> str:
    if not chapter_ids:
        raise BatchError("a batch needs at least one chapter")
    ordered = sorted(chapter_ids)
    if len(ordered) == 1:
        return f"batch-{ordered[0]}"
    return f"batch-{ordered[0]}-{ordered[-1]}"


def batch_filename(chapter_ids: Sequence[str]) -> str:
    return f"{batch_id_for(chapter_ids)}.json"


def ordered_chapter_ids() -> tuple[str, ...]:
    return tuple(f"CH{number:03d}" for number in range(1, CURRICULUM_CHAPTERS + 1))


def next_batch_chapter_ids(
    completed: Iterable[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    include_samples: bool = False,
) -> tuple[str, ...]:
    """Return the next contiguous run of chapters still to generate."""

    if batch_size < 1:
        raise BatchError("batch_size must be positive")
    done = set(completed)
    pending = [
        chapter_id
        for chapter_id in ordered_chapter_ids()
        if chapter_id not in done
        and (include_samples or chapter_id not in APPROVED_SAMPLE_CHAPTERS)
    ]
    return tuple(pending[:batch_size])


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_batch(
    root: str | Path,
    chapters: Sequence[Chapter],
    *,
    continuity: ContinuityState | None = None,
    overwrite: bool = False,
) -> BatchFile:
    """Write one batch document and return its hash-backed record."""

    if not chapters:
        raise BatchError("cannot write an empty batch")
    chapter_ids = tuple(chapter.article_id for chapter in chapters)
    if len(set(chapter_ids)) != len(chapter_ids):
        raise BatchError("batch contains duplicate chapter ids")
    if list(chapter_ids) != sorted(chapter_ids):
        raise BatchError("batch chapters must be written in chapter order")
    if continuity is not None and continuity.chapter_id != chapter_ids[-1]:
        raise BatchError(
            "batch boundary record must describe the last chapter of the batch "
            f"({chapter_ids[-1]}), got {continuity.chapter_id}"
        )

    target = batches_dir(root) / batch_filename(chapter_ids)
    if target.exists() and not overwrite:
        raise BatchError(f"batch already exists and was not overwritten: {target}")
    document: dict[str, Any] = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "batch_id": batch_id_for(chapter_ids),
        "chapter_ids": list(chapter_ids),
        "chapters": [chapter.to_dict() for chapter in chapters],
    }
    if continuity is not None:
        document["continuity"] = state_to_dict(continuity)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return BatchFile(
        path=target,
        batch_id=document["batch_id"],
        chapter_ids=chapter_ids,
        sha256=compute_sha256(target),
        chapters=tuple(chapters),
        continuity=continuity,
    )


def load_batch(path: str | Path) -> BatchFile:
    """Load one batch document, rejecting schema drift or id mismatches."""

    batch_path = Path(path)
    document = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise BatchError(f"{batch_path}: batch document must be an object")
    if document.get("schema_version") != BATCH_SCHEMA_VERSION:
        raise BatchError(f"{batch_path}: unsupported batch schema version")
    raw_chapters = document.get("chapters")
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raise BatchError(f"{batch_path}: batch must contain chapters")
    chapters = tuple(Chapter.from_dict(entry) for entry in raw_chapters)
    chapter_ids = tuple(chapter.article_id for chapter in chapters)
    declared = document.get("chapter_ids")
    if declared is not None and tuple(declared) != chapter_ids:
        raise BatchError(f"{batch_path}: chapter_ids do not match the chapter records")
    batch_id = document.get("batch_id") or batch_id_for(chapter_ids)
    raw_continuity = document.get("continuity")
    continuity = None
    if raw_continuity is not None:
        continuity = state_from_dict(raw_continuity)
        if continuity.chapter_id != chapter_ids[-1]:
            raise BatchError(
                f"{batch_path}: boundary record must describe {chapter_ids[-1]}, "
                f"got {continuity.chapter_id}"
            )
    return BatchFile(
        path=batch_path,
        batch_id=str(batch_id),
        chapter_ids=chapter_ids,
        sha256=compute_sha256(batch_path),
        chapters=chapters,
        continuity=continuity,
    )


def load_batches(root: str | Path) -> Mapping[str, BatchFile]:
    """Load every batch document in the batch directory, keyed by batch id."""

    directory = batches_dir(root)
    if not directory.is_dir():
        return {}
    batches: dict[str, BatchFile] = {}
    for path in sorted(directory.glob("batch-*.json")):
        batch = load_batch(path)
        if batch.batch_id in batches:
            raise BatchError(f"duplicate batch id {batch.batch_id}")
        batches[batch.batch_id] = batch
    return batches


def completed_chapter_ids(root: str | Path) -> tuple[str, ...]:
    """Every chapter id already persisted in a batch document or approved sample."""

    owners: dict[str, str] = {}
    for batch in load_batches(root).values():
        for chapter_id in batch.chapter_ids:
            if chapter_id in owners:
                raise BatchError(
                    f"chapter {chapter_id} appears in both {owners[chapter_id]} "
                    f"and {batch.batch_id}"
                )
            owners[chapter_id] = batch.batch_id
    return tuple(sorted(set(owners) | set(APPROVED_SAMPLE_CHAPTERS)))


def load_checkpoint(root: str | Path) -> Checkpoint:
    """Load the checkpoint, returning an empty one when none exists yet."""

    path = batches_dir(root) / CHECKPOINT_FILENAME
    if not path.is_file():
        return Checkpoint()
    return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_checkpoint(root: str | Path, checkpoint: Checkpoint) -> Path:
    path = batches_dir(root) / CHECKPOINT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def rebuild_checkpoint(root: str | Path) -> Checkpoint:
    """Reconstruct the checkpoint from the batch files actually on disk."""

    batch_hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    completed: list[str] = list(APPROVED_SAMPLE_CHAPTERS)
    for batch_id, batch in sorted(load_batches(root).items()):
        batch_hashes[batch_id] = batch.sha256
        completed.extend(batch.chapter_ids)
        counts["chapters_in_batches"] = counts.get("chapters_in_batches", 0) + len(
            batch.chapter_ids
        )
    completed = sorted(set(completed))
    counts["complete_chapters"] = len(completed)
    counts["batches"] = len(batch_hashes)
    pending = next_batch_chapter_ids(completed)
    return Checkpoint(
        completed_chapter_ids=tuple(completed),
        batch_hashes=batch_hashes,
        validation_counts=counts,
        next_chapter_id=pending[0] if pending else None,
    )


def verify_batch_integrity(root: str | Path, checkpoint: Checkpoint) -> list[str]:
    """Confirm every checkpointed batch still matches the bytes on disk."""

    problems: list[str] = []
    directory = batches_dir(root)
    for batch_id, expected in checkpoint.batch_hashes.items():
        matches = list(directory.glob(f"{batch_id}.json"))
        if not matches:
            problems.append(f"checkpointed batch is missing on disk: {batch_id}")
            continue
        actual = compute_sha256(matches[0])
        if actual != expected:
            problems.append(
                f"batch {batch_id} hash changed: expected {expected}, got {actual}"
            )
    return problems


def _schema_errors(root: Path, chapters: Sequence[Chapter]) -> list[str]:
    schema_path = root / "source" / "cet4_story" / "schemas" / "chapter.schema.json"
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - depends on the dev extra
        raise BatchError(
            "jsonschema is required for batch validation; run `uv sync --extra dev`"
        ) from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for chapter in chapters:
        for error in sorted(validator.iter_errors(chapter.to_dict()), key=str):
            errors.append(f"{chapter.article_id}: schema: {error.message}")
    return errors


def validate_batch(
    chapters: Sequence[Chapter],
    project: ProjectData,
    *,
    batch_id: str | None = None,
    previous_state: ContinuityState | None = None,
    current_state: ContinuityState | None = None,
    require_continuity: bool = True,
) -> BatchValidation:
    """Validate one batch against the protected sources and the schema."""

    if not chapters:
        raise BatchError("cannot validate an empty batch")
    chapter_ids = tuple(chapter.article_id for chapter in chapters)
    identifier = batch_id or batch_id_for(chapter_ids)

    errors: list[str] = []
    errors.extend(_schema_errors(project.root, chapters))

    validator = project.validator()
    reports: list[ChapterValidationReport] = []
    occurrences: list[CoverageOccurrence] = []
    coverage_errors: list[str] = []
    structural_errors: list[str] = []
    for chapter in chapters:
        report = validator.check(chapter)
        reports.append(report)
        occurrences.extend(report.coverage_occurrences)
        for message in report.errors:
            if COVERAGE_ERROR_PHRASE in message:
                coverage_errors.append(message)
            else:
                structural_errors.append(message)

    continuity_errors: list[str] = []
    if require_continuity:
        if current_state is None:
            continuity_errors.append(
                f"{identifier}: batch boundary continuity record is required"
            )
        else:
            try:
                cast = parse_cast(project.source.character_guide)
            except ValueError as exc:
                continuity_errors.append(f"{identifier}: {exc}")
                cast = ()
            continuity_errors.extend(
                check_boundary(
                    previous_state,
                    current_state,
                    cast=cast,
                    expected_first_chapter=chapter_ids[-1],
                )
            )

    unverified = [item for item in occurrences if item.status != "verified"]
    coverage_valid = not unverified and not coverage_errors
    result = BatchValidationResult(
        batch_id=identifier,
        chapter_ids=chapter_ids,
        schema_valid=not errors,
        plan_valid=not structural_errors,
        coverage_valid=coverage_valid,
        continuity_valid=not continuity_errors,
        validation_counts={
            "chapters": len(chapters),
            "coverage_records": len(occurrences),
            "verified_new": sum(
                1 for item in occurrences if item.kind == "new" and item.status == "verified"
            ),
            "verified_review": sum(
                1
                for item in occurrences
                if item.kind == "review" and item.status == "verified"
            ),
            "needs_revision": len(unverified),
            "structural_errors": len(structural_errors),
            "continuity_errors": len(continuity_errors),
        },
        errors=tuple(errors + structural_errors + coverage_errors + continuity_errors),
    )
    return BatchValidation(
        result=result, reports=tuple(reports), occurrences=tuple(occurrences)
    )


def commit_batch(
    root: str | Path,
    batch: BatchFile,
    validation: BatchValidation,
    *,
    checkpoint: Checkpoint | None = None,
) -> Checkpoint:
    """Persist a validated batch in the checkpoint, refusing invalid work."""

    if not validation.result.is_valid:
        if validation.reports:
            raise ChapterValidationError(
                list(validation.result.errors), validation.reports[0]
            )
        raise BatchError("batch validation failed")
    current = checkpoint or load_checkpoint(root)
    completed = sorted(
        set(current.completed_chapter_ids) | set(batch.chapter_ids) | set(APPROVED_SAMPLE_CHAPTERS)
    )
    counts = dict(current.validation_counts)
    for key, value in validation.result.validation_counts.items():
        if key in {"chapters", "coverage_records", "verified_new", "verified_review", "needs_revision"}:
            counts[key] = counts.get(key, 0) + value
    counts["batches"] = counts.get("batches", 0) + 1
    counts["complete_chapters"] = len(completed)
    pending = next_batch_chapter_ids(completed)
    updated = Checkpoint(
        completed_chapter_ids=tuple(completed),
        batch_hashes={**current.batch_hashes, batch.batch_id: batch.sha256},
        validation_counts=counts,
        next_chapter_id=pending[0] if pending else None,
    )
    save_checkpoint(root, updated)
    return updated


def continuity_path(root: str | Path) -> Path:
    return batches_dir(root) / CONTINUITY_FILENAME


def record_boundary(
    root: str | Path,
    state: ContinuityState,
    *,
    previous_state: ContinuityState | None = None,
    allow_replace: bool = True,
) -> ContinuityState:
    """Append one validated boundary record to the continuity log."""

    states = dict(load_continuity(continuity_path(root)))
    existing = states.get(state.chapter_id)
    if existing is not None and not allow_replace:
        raise BatchError(f"continuity record already exists for {state.chapter_id}")
    if previous_state is not None and existing is None:
        latest = max(states.values(), key=lambda item: item.chapter_id, default=None)
        if latest is not None and latest.chapter_id != previous_state.chapter_id:
            raise BatchError(
                "continuity log is not contiguous: last record is "
                f"{latest.chapter_id}, expected {previous_state.chapter_id}"
            )
    states[state.chapter_id] = state
    save_continuity(continuity_path(root), states)
    return state


__all__ = [
    "APPROVED_SAMPLE_CHAPTERS",
    "BATCH_DIR",
    "BATCH_SCHEMA_VERSION",
    "CHECKPOINT_FILENAME",
    "DEFAULT_BATCH_SIZE",
    "BatchError",
    "BatchFile",
    "BatchValidation",
    "batch_filename",
    "batch_id_for",
    "batches_dir",
    "commit_batch",
    "completed_chapter_ids",
    "compute_sha256",
    "continuity_path",
    "load_batch",
    "load_batches",
    "load_checkpoint",
    "next_batch_chapter_ids",
    "ordered_chapter_ids",
    "rebuild_checkpoint",
    "record_boundary",
    "save_checkpoint",
    "validate_batch",
    "verify_batch_integrity",
    "write_batch",
]
