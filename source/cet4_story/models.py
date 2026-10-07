"""Typed, JSON-serializable records for the CET-4 curriculum pipeline.

The persisted chapter shape intentionally mirrors ``chapter.schema.json``.  The
remaining records are shared contracts for matching, continuity validation,
batch validation, and recoverable checkpointing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence, TypeAlias
import re

JsonObject: TypeAlias = dict[str, Any]
CoverageKind: TypeAlias = Literal["new", "review"]
CoverageStatus: TypeAlias = Literal[
    "planned", "generated", "reviewed", "verified", "needs_revision"
]

_ARTICLE_ID = re.compile(r"^CH\d{3}$")
_EXERCISE_ID = re.compile(r"^(CH\d{3})-Q([1-5])$")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be an array")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must not be blank")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(_sequence(value, label)))


def _reject_extra(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(data) - allowed)
    if extras:
        raise ValueError(f"{label} has unknown fields: {', '.join(extras)}")


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One aligned English/Chinese paragraph pair; ``index`` is one-based."""

    index: int
    english: str
    chinese: str

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("paragraph index must be positive")
        _text(self.english, "paragraph english text")
        _text(self.chinese, "paragraph chinese text")


@dataclass(frozen=True, slots=True)
class Exercise:
    id: str
    type: str
    prompt: str
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _EXERCISE_ID.fullmatch(self.id):
            raise ValueError(f"invalid exercise id: {self.id!r}")
        _text(self.type, "exercise type")
        _text(self.prompt, "exercise prompt")
        if self.options and len(self.options) < 2:
            raise ValueError("exercise options must contain at least two items")
        if len(set(self.options)) != len(self.options):
            raise ValueError("exercise options must be unique")
        for index, option in enumerate(self.options):
            _text(option, f"exercise options[{index}]")

    @classmethod
    def from_dict(cls, value: object) -> Exercise:
        data = _mapping(value, "exercise")
        _reject_extra(data, {"id", "type", "prompt", "options"}, "exercise")
        return cls(
            id=_text(data.get("id"), "exercise id"),
            type=_text(data.get("type"), "exercise type"),
            prompt=_text(data.get("prompt"), "exercise prompt"),
            options=_string_tuple(data["options"], "exercise options") if "options" in data else (),
        )

    def to_dict(self) -> JsonObject:
        result: JsonObject = {"id": self.id, "type": self.type, "prompt": self.prompt}
        if self.options:
            result["options"] = list(self.options)
        return result


@dataclass(frozen=True, slots=True)
class Answer:
    id: str
    answer: str
    explanation: str

    def __post_init__(self) -> None:
        if not _EXERCISE_ID.fullmatch(self.id):
            raise ValueError(f"invalid answer id: {self.id!r}")
        _text(self.answer, "answer")
        _text(self.explanation, "answer explanation")

    @classmethod
    def from_dict(cls, value: object) -> Answer:
        data = _mapping(value, "answer")
        _reject_extra(data, {"id", "answer", "explanation"}, "answer")
        return cls(
            id=_text(data.get("id"), "answer id"),
            answer=_text(data.get("answer"), "answer"),
            explanation=_text(data.get("explanation"), "answer explanation"),
        )

    def to_dict(self) -> JsonObject:
        return {"id": self.id, "answer": self.answer, "explanation": self.explanation}


@dataclass(frozen=True, slots=True)
class Chapter:
    """A chapter in the exact persisted shape used by approved samples."""

    article_id: str
    english_title: str
    chinese_title: str
    theme: str
    english_paragraphs: tuple[str, ...]
    chinese_paragraphs: tuple[str, ...]
    exercises: tuple[Exercise, ...]
    answers: tuple[Answer, ...]

    def __post_init__(self) -> None:
        if not _ARTICLE_ID.fullmatch(self.article_id):
            raise ValueError(f"invalid article id: {self.article_id!r}")
        _text(self.english_title, "English title")
        _text(self.chinese_title, "Chinese title")
        _text(self.theme, "theme")
        if len(self.english_paragraphs) != len(self.chinese_paragraphs):
            raise ValueError("English and Chinese paragraph counts must match")
        if not 4 <= len(self.english_paragraphs) <= 6:
            raise ValueError("chapters must contain four to six aligned paragraphs")
        for paragraph in self.paragraphs:
            # Constructing the paired record performs the text checks.
            _ = paragraph
        if len(self.exercises) != 5 or len(self.answers) != 5:
            raise ValueError("chapters must contain exactly five exercises and five answers")
        expected_ids = tuple(f"{self.article_id}-Q{number}" for number in range(1, 6))
        exercise_ids = tuple(exercise.id for exercise in self.exercises)
        answer_ids = tuple(answer.id for answer in self.answers)
        if exercise_ids != expected_ids:
            raise ValueError(f"exercise ids must be ordered as {expected_ids!r}")
        if answer_ids != expected_ids:
            raise ValueError(f"answer ids must be ordered as {expected_ids!r}")

    @property
    def paragraphs(self) -> tuple[Paragraph, ...]:
        return tuple(
            Paragraph(index=index, english=english, chinese=chinese)
            for index, (english, chinese) in enumerate(
                zip(self.english_paragraphs, self.chinese_paragraphs, strict=True), start=1
            )
        )

    @classmethod
    def from_dict(cls, value: object) -> Chapter:
        data = _mapping(value, "chapter")
        allowed = {
            "article_id", "english_title", "chinese_title", "theme",
            "english_paragraphs", "chinese_paragraphs", "exercises", "answers",
        }
        _reject_extra(data, allowed, "chapter")
        return cls(
            article_id=_text(data.get("article_id"), "article id"),
            english_title=_text(data.get("english_title"), "English title"),
            chinese_title=_text(data.get("chinese_title"), "Chinese title"),
            theme=_text(data.get("theme"), "theme"),
            english_paragraphs=_string_tuple(data.get("english_paragraphs"), "English paragraphs"),
            chinese_paragraphs=_string_tuple(data.get("chinese_paragraphs"), "Chinese paragraphs"),
            exercises=tuple(
                Exercise.from_dict(item)
                for item in _sequence(data.get("exercises"), "exercises")
            ),
            answers=tuple(
                Answer.from_dict(item)
                for item in _sequence(data.get("answers"), "answers")
            ),
        )

    def to_dict(self) -> JsonObject:
        return {
            "article_id": self.article_id,
            "english_title": self.english_title,
            "chinese_title": self.chinese_title,
            "theme": self.theme,
            "english_paragraphs": list(self.english_paragraphs),
            "chinese_paragraphs": list(self.chinese_paragraphs),
            "exercises": [exercise.to_dict() for exercise in self.exercises],
            "answers": [answer.to_dict() for answer in self.answers],
        }


@dataclass(frozen=True, slots=True)
class CoverageOccurrence:
    """Auditable evidence for one planned vocabulary occurrence."""

    vocabulary_id: str
    lemma: str
    article_id: str
    status: CoverageStatus
    occurrence_count: int
    original_form: str | None
    matched_form: str | None
    match_method: str | None
    context_sentence: str | None
    review_note: str | None
    kind: CoverageKind = "new"
    paragraph_index: int | None = None

    def __post_init__(self) -> None:
        _text(self.vocabulary_id, "vocabulary id")
        _text(self.lemma, "lemma")
        if not _ARTICLE_ID.fullmatch(self.article_id):
            raise ValueError(f"invalid article id: {self.article_id!r}")
        if self.kind not in ("new", "review"):
            raise ValueError(f"invalid coverage kind: {self.kind!r}")
        if self.status not in (
            "planned", "generated", "reviewed", "verified", "needs_revision"
        ):
            raise ValueError(f"invalid coverage status: {self.status!r}")
        if self.occurrence_count < 0:
            raise ValueError("occurrence count must not be negative")
        if self.paragraph_index is not None and self.paragraph_index < 1:
            raise ValueError("coverage paragraph index must be positive")
        for value, label in (
            (self.original_form, "original form"),
            (self.matched_form, "matched form"),
            (self.match_method, "match method"),
            (self.context_sentence, "context sentence"),
            (self.review_note, "review note"),
        ):
            if value is not None:
                _text(value, label)
        if self.status == "verified":
            _text(self.original_form, "original form")
            _text(self.matched_form, "matched form")
            _text(self.match_method, "match method")
            _text(self.context_sentence, "context sentence")
            if self.occurrence_count < 1:
                raise ValueError("verified coverage requires at least one occurrence")
            if self.paragraph_index is None:
                raise ValueError("verified coverage requires a paragraph index")

    @property
    def chapter_id(self) -> str:
        """Compatibility alias for code that uses chapter terminology."""

        return self.article_id


@dataclass(frozen=True, slots=True)
class ContinuityState:
    """Story facts required to validate a chapter boundary."""

    chapter_id: str
    last_event: str
    unresolved_consequence: str | None = None
    character_locations: Mapping[str, str] = field(default_factory=dict)
    character_roles: Mapping[str, str] = field(default_factory=dict)
    open_commitments: tuple[str, ...] = ()
    open_conflicts: tuple[str, ...] = ()
    first_required_event_next_chapter: str | None = None
    established_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _ARTICLE_ID.fullmatch(self.chapter_id):
            raise ValueError(f"invalid chapter id: {self.chapter_id!r}")
        _text(self.last_event, "last event")
        if self.unresolved_consequence is not None:
            _text(self.unresolved_consequence, "unresolved consequence")
        if self.first_required_event_next_chapter is not None:
            _text(
                self.first_required_event_next_chapter,
                "first required event for the next chapter",
            )
        for label, values in (
            ("open commitments", self.open_commitments),
            ("open conflicts", self.open_conflicts),
            ("established facts", self.established_facts),
        ):
            for index, value in enumerate(values):
                _text(value, f"{label}[{index}]")
        for label, values in (
            ("character location", self.character_locations),
            ("character role", self.character_roles),
        ):
            for name, value in values.items():
                _text(name, "character name")
                _text(value, f"{label} for {name}")

    @property
    def next_chapter_first_required_event(self) -> str | None:
        """Readable alias for the persisted boundary field."""

        return self.first_required_event_next_chapter

    @property
    def first_required_event(self) -> str | None:
        """Short alias used by continuity validators."""

        return self.first_required_event_next_chapter


@dataclass(frozen=True, slots=True)
class BatchValidationResult:
    """Deterministic validation outcome for one generated batch."""

    batch_id: str
    chapter_ids: tuple[str, ...]
    schema_valid: bool
    plan_valid: bool
    coverage_valid: bool
    continuity_valid: bool
    validation_counts: Mapping[str, int] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.batch_id, "batch id")
        if not self.chapter_ids:
            raise ValueError("batch validation must include at least one chapter")
        if len(set(self.chapter_ids)) != len(self.chapter_ids):
            raise ValueError("batch chapter ids must be unique")
        if any(not _ARTICLE_ID.fullmatch(chapter_id) for chapter_id in self.chapter_ids):
            raise ValueError("batch contains an invalid chapter id")
        if any(count < 0 for count in self.validation_counts.values()):
            raise ValueError("validation counts must not be negative")

    @property
    def is_valid(self) -> bool:
        return (
            self.schema_valid
            and self.plan_valid
            and self.coverage_valid
            and self.continuity_valid
            and not self.errors
        )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Recoverable state written only after complete batch validation."""

    completed_chapter_ids: tuple[str, ...] = ()
    batch_hashes: Mapping[str, str] = field(default_factory=dict)
    validation_counts: Mapping[str, int] = field(default_factory=dict)
    next_chapter_id: str | None = "CH001"
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("checkpoint version must be positive")
        if len(set(self.completed_chapter_ids)) != len(self.completed_chapter_ids):
            raise ValueError("completed chapter ids must be unique")
        if any(not _ARTICLE_ID.fullmatch(chapter_id) for chapter_id in self.completed_chapter_ids):
            raise ValueError("checkpoint contains an invalid chapter id")
        if self.next_chapter_id is not None and not _ARTICLE_ID.fullmatch(self.next_chapter_id):
            raise ValueError(f"invalid next chapter id: {self.next_chapter_id!r}")
        if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in self.batch_hashes.values()):
            raise ValueError("batch hashes must be lowercase SHA-256 digests")
        if any(count < 0 for count in self.validation_counts.values()):
            raise ValueError("checkpoint validation counts must not be negative")

    @classmethod
    def from_dict(cls, value: object) -> Checkpoint:
        data = _mapping(value, "checkpoint")
        allowed = {
            "version", "completed_chapter_ids", "batch_hashes",
            "validation_counts", "next_chapter_id",
        }
        _reject_extra(data, allowed, "checkpoint")
        batch_hashes = _mapping(data.get("batch_hashes", {}), "batch hashes")
        validation_counts = _mapping(data.get("validation_counts", {}), "validation counts")
        version = data.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            raise TypeError("checkpoint version must be an integer")
        if any(not isinstance(count, int) or isinstance(count, bool) for count in validation_counts.values()):
            raise TypeError("validation counts must be integers")
        return cls(
            version=version,
            completed_chapter_ids=_string_tuple(
                data.get("completed_chapter_ids", ()), "completed chapter ids"
            ),
            batch_hashes={
                _text(key, "batch hash key"): _text(digest, f"hash for {key}")
                for key, digest in batch_hashes.items()
            },
            validation_counts={str(key): count for key, count in validation_counts.items()},
            next_chapter_id=(
                None if data.get("next_chapter_id") is None
                else _text(data.get("next_chapter_id"), "next chapter id")
            ),
        )

    def to_dict(self) -> JsonObject:
        return {
            "version": self.version,
            "completed_chapter_ids": list(self.completed_chapter_ids),
            "batch_hashes": dict(self.batch_hashes),
            "validation_counts": dict(self.validation_counts),
            "next_chapter_id": self.next_chapter_id,
        }


# Explicit aliases make the records easy to discover without coupling callers to
# one naming convention.
ParagraphRecord = Paragraph
ExerciseRecord = Exercise
AnswerRecord = Answer
ChapterRecord = Chapter
CoverageOccurrenceRecord = CoverageOccurrence
ContinuityStateRecord = ContinuityState
CheckpointRecord = Checkpoint

__all__ = [
    "Answer", "AnswerRecord", "BatchValidationResult", "Chapter", "ChapterRecord",
    "Checkpoint", "CheckpointRecord", "ContinuityState", "ContinuityStateRecord",
    "CoverageKind", "CoverageOccurrence", "CoverageOccurrenceRecord", "CoverageStatus",
    "Exercise", "ExerciseRecord", "JsonObject", "Paragraph", "ParagraphRecord",
]
