"""Deterministic validation for generated CET-4 curriculum chapters.

The validator treats the protected curriculum plan and vocabulary table as the
source of truth.  Vocabulary evidence is collected only from English story
paragraphs through :mod:`cet4_story.matching`; titles, exercises, answers, and
other metadata can never satisfy coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Mapping, Sequence

from .matching import MatchingError, match_vocabulary_record
from .models import Chapter, CoverageOccurrence
from .source_data import ProtectedSourceData

MIN_ENGLISH_WORDS = 350
MAX_ENGLISH_WORDS = 450
MIN_PARAGRAPHS = 4
MAX_PARAGRAPHS = 6
EXERCISE_COUNT = 5

_WORD = re.compile(r"[A-Za-z]+(?:[-'’][A-Za-z]+)*")
_ID_LIST_DELIMITERS = (";", "|", ",")
_NEW_ID_FIELDS = (
    "new_vocabulary_ids",
    "new_vocab_ids",
    "new_word_ids",
    "assigned_vocabulary_ids",
)
_REVIEW_ID_FIELDS = (
    "review_vocabulary_ids",
    "review_vocab_ids",
    "review_word_ids",
)
_LEMMA_FIELDS = ("word", "lemma", "headword")
_EXCHANGE_FIELDS = ("exchange", "ecdict_exchange")


class ChapterValidationError(ValueError):
    """A chapter failed one or more deterministic acceptance checks."""

    def __init__(self, errors: Sequence[str], report: ChapterValidationReport) -> None:
        self.errors = tuple(errors)
        self.report = report
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True, slots=True)
class ChapterValidationReport:
    """Complete deterministic evidence for one chapter validation run."""

    chapter_id: str
    word_count: int
    paragraph_count: int
    exercise_count: int
    answer_count: int
    coverage_occurrences: tuple[CoverageOccurrence, ...]
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def occurrences(self) -> tuple[CoverageOccurrence, ...]:
        """Short compatibility alias for coverage-report consumers."""

        return self.coverage_occurrences

    @property
    def validation_counts(self) -> Mapping[str, int]:
        verified = sum(
            occurrence.status == "verified"
            for occurrence in self.coverage_occurrences
        )
        return {
            "chapters": 1,
            "english_words": self.word_count,
            "paragraph_pairs": self.paragraph_count,
            "exercises": self.exercise_count,
            "answers": self.answer_count,
            "coverage_targets": len(self.coverage_occurrences),
            "coverage_verified": verified,
            "coverage_needs_revision": len(self.coverage_occurrences) - verified,
            "errors": len(self.errors),
        }


def count_english_words(chapter: Chapter | Mapping[str, object]) -> int:
    """Count English story words, excluding all non-story chapter sections."""

    paragraphs: object
    if isinstance(chapter, Chapter):
        paragraphs = chapter.english_paragraphs
    elif isinstance(chapter, Mapping):
        paragraphs = chapter.get("english_paragraphs")
    else:
        raise TypeError("chapter must be a Chapter or mapping")
    if isinstance(paragraphs, (str, bytes)) or not isinstance(paragraphs, Sequence):
        raise TypeError("english_paragraphs must be an array")

    total = 0
    for index, paragraph in enumerate(paragraphs):
        if not isinstance(paragraph, str):
            raise TypeError(f"english_paragraphs[{index}] must be a string")
        total += len(_WORD.findall(paragraph))
    return total


def _required_plan_text(
    plan: Mapping[str, str], fields: Sequence[str], label: str
) -> str:
    for field in fields:
        if field in plan:
            value = plan[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"plan {label} must not be blank")
            return value
    raise ValueError(f"plan is missing {label} ({', '.join(fields)})")


def _parse_id_list(value: object, *, label: str) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    parsed: object = value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in plan {label}: {exc}") from exc
        else:
            for delimiter in _ID_LIST_DELIMITERS:
                if delimiter in stripped:
                    parsed = [part.strip() for part in stripped.split(delimiter)]
                    break
            else:
                parsed = [stripped]

    if isinstance(parsed, (str, bytes)) or not isinstance(parsed, Sequence):
        raise ValueError(f"plan {label} must be an array of vocabulary IDs")
    result: list[str] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"plan {label}[{index}] must be a nonblank string")
        result.append(item)
    if len(set(result)) != len(result):
        raise ValueError(f"plan {label} contains duplicate vocabulary IDs")
    return tuple(result)


def _plan_ids(
    plan: Mapping[str, str], fields: Sequence[str], label: str
) -> tuple[str, ...]:
    for field in fields:
        if field in plan:
            return _parse_id_list(plan[field], label=label)
    if label == "review_vocabulary_ids":
        return ()
    raise ValueError(f"plan is missing {label} ({', '.join(fields)})")


def _chapter_id_from_input(chapter: Chapter | Mapping[str, object]) -> str:
    if isinstance(chapter, Chapter):
        return chapter.article_id
    value = chapter.get("article_id")
    return value if isinstance(value, str) else "<unknown>"


def _resolve_plan_and_vocabulary(
    chapter_id: str,
    plan_or_source: Mapping[str, str] | ProtectedSourceData,
    vocabulary_by_id: Mapping[str, Mapping[str, str]] | None,
) -> tuple[Mapping[str, str], Mapping[str, Mapping[str, str]]]:
    if isinstance(plan_or_source, ProtectedSourceData):
        if vocabulary_by_id is not None:
            raise TypeError(
                "vocabulary_by_id must not be passed with ProtectedSourceData"
            )
        return (
            plan_or_source.chapter_record(chapter_id),
            plan_or_source.vocabulary_by_id,
        )
    if not isinstance(plan_or_source, Mapping):
        raise TypeError("plan_or_source must be a plan row or ProtectedSourceData")
    if vocabulary_by_id is None:
        raise TypeError("vocabulary_by_id is required when passing a plan row")
    return plan_or_source, vocabulary_by_id


def _record_fields(
    vocabulary_id: str, record: Mapping[str, str]
) -> tuple[str, str, str]:
    id_field = next(
        (
            field
            for field in ("vocabulary_id", "word_id", "vocab_id", "id")
            if field in record
        ),
        None,
    )
    if id_field is None:
        raise ValueError(f"vocabulary record {vocabulary_id!r} has no ID field")
    if record[id_field] != vocabulary_id:
        raise ValueError(
            f"vocabulary index key {vocabulary_id!r} does not match record ID "
            f"{record[id_field]!r}"
        )
    lemma_field = next((field for field in _LEMMA_FIELDS if field in record), None)
    if lemma_field is None or not record[lemma_field].strip():
        raise ValueError(f"vocabulary record {vocabulary_id!r} has no lemma")
    exchange_field = next(
        (field for field in _EXCHANGE_FIELDS if field in record), "exchange"
    )
    return id_field, lemma_field, exchange_field


def generate_coverage_occurrences(
    chapter: Chapter,
    plan: Mapping[str, str],
    vocabulary_by_id: Mapping[str, Mapping[str, str]],
) -> tuple[CoverageOccurrence, ...]:
    """Generate one auditable story-scope occurrence per planned target.

    New targets are returned first in protected plan order, followed by review
    targets in protected plan order. Unknown IDs, duplicate allocations, and
    malformed vocabulary records are rejected rather than silently omitted.
    """

    new_ids = _plan_ids(plan, _NEW_ID_FIELDS, "new_vocabulary_ids")
    review_ids = _plan_ids(plan, _REVIEW_ID_FIELDS, "review_vocabulary_ids")
    overlap = sorted(set(new_ids) & set(review_ids))
    if overlap:
        raise ValueError(
            "plan lists vocabulary IDs as both new and review: " + ", ".join(overlap)
        )

    occurrences: list[CoverageOccurrence] = []
    for kind, vocabulary_ids in (("new", new_ids), ("review", review_ids)):
        for vocabulary_id in vocabulary_ids:
            try:
                record = vocabulary_by_id[vocabulary_id]
            except KeyError as exc:
                raise ValueError(
                    f"plan references unknown vocabulary ID {vocabulary_id!r}"
                ) from exc
            id_field, lemma_field, exchange_field = _record_fields(
                vocabulary_id, record
            )
            occurrences.append(
                match_vocabulary_record(
                    chapter,
                    record,
                    id_field=id_field,
                    lemma_field=lemma_field,
                    exchange_field=exchange_field,
                    kind=kind,
                )
            )
    return tuple(occurrences)


def _check_plan_metadata(
    chapter: Chapter, plan: Mapping[str, str], errors: list[str]
) -> None:
    try:
        planned_chapter_id = _required_plan_text(
            plan, ("chapter_id", "article_id"), "chapter ID"
        )
        planned_title = _required_plan_text(
            plan, ("title", "english_title"), "title"
        )
        planned_theme = _required_plan_text(plan, ("theme",), "theme")
        # Plot summary is binding generation metadata even though the approved
        # persisted sample shape does not duplicate it in each chapter.
        _required_plan_text(plan, ("plot_summary",), "plot summary")
    except ValueError as exc:
        errors.append(str(exc))
        return

    comparisons = (
        ("article_id", chapter.article_id, planned_chapter_id),
        ("english_title", chapter.english_title, planned_title),
        ("theme", chapter.theme, planned_theme),
    )
    for label, actual, expected in comparisons:
        if actual != expected:
            errors.append(
                f"{chapter.article_id}: {label} does not match the protected plan "
                f"(expected {expected!r}, got {actual!r})"
            )

    if "chinese_title" in plan:
        planned_chinese_title = plan["chinese_title"]
        if chapter.chinese_title != planned_chinese_title:
            errors.append(
                f"{chapter.article_id}: chinese_title does not match the protected "
                f"plan (expected {planned_chinese_title!r}, got "
                f"{chapter.chinese_title!r})"
            )


def _answer_pattern(answer: str) -> re.Pattern[str]:
    """Build a case-insensitive whole-answer pattern for prompt leakage checks."""

    pieces = re.split(r"\s+", answer.strip())
    body = r"\s+".join(re.escape(piece) for piece in pieces)
    return re.compile(rf"(?<![\w'’-]){body}(?![\w'’-])", re.IGNORECASE)


def _answer_leakage_errors(chapter: Chapter) -> list[str]:
    """Reject prompts that disclose the answer paired with their exercise ID."""

    answers_by_id = {answer.id: answer for answer in chapter.answers}
    errors: list[str] = []
    for exercise in chapter.exercises:
        answer = answers_by_id[exercise.id]
        if _answer_pattern(answer.answer).search(exercise.prompt):
            errors.append(
                f"{chapter.article_id}: exercise {exercise.id} prompt contains its "
                "matching answer; answers must remain outside exercise text"
            )
    return errors


def _coverage_errors(
    chapter_id: str, occurrences: Sequence[CoverageOccurrence]
) -> list[str]:
    errors: list[str] = []
    for occurrence in occurrences:
        if occurrence.status == "verified":
            continue
        detail = occurrence.review_note or "coverage could not be verified"
        errors.append(
            f"{chapter_id}: planned {occurrence.kind} vocabulary "
            f"{occurrence.vocabulary_id} ({occurrence.lemma!r}) is not verified "
            f"in English story text: {detail}"
        )
    return errors


def check_chapter(
    chapter: Chapter | Mapping[str, object],
    plan_or_source: Mapping[str, str] | ProtectedSourceData,
    vocabulary_by_id: Mapping[str, Mapping[str, str]] | None = None,
    *,
    min_words: int = MIN_ENGLISH_WORDS,
    max_words: int = MAX_ENGLISH_WORDS,
) -> ChapterValidationReport:
    """Run all checks and return a report without raising for invalid content."""

    if min_words < 0 or max_words < min_words:
        raise ValueError("word-count bounds are invalid")

    errors: list[str] = []
    chapter_id = _chapter_id_from_input(chapter)
    try:
        model = chapter if isinstance(chapter, Chapter) else Chapter.from_dict(chapter)
    except (TypeError, ValueError) as exc:
        errors.append(f"{chapter_id}: invalid chapter structure: {exc}")
        return ChapterValidationReport(
            chapter_id=chapter_id,
            word_count=0,
            paragraph_count=0,
            exercise_count=0,
            answer_count=0,
            coverage_occurrences=(),
            errors=tuple(errors),
        )

    word_count = count_english_words(model)
    if not min_words <= word_count <= max_words:
        errors.append(
            f"{model.article_id}: English story word count must be {min_words}-"
            f"{max_words}; got {word_count}"
        )
    errors.extend(_answer_leakage_errors(model))

    # Chapter.__post_init__ enforces 4-6 aligned paragraphs, five exercises,
    # five answers, and ordered one-to-one exercise/answer IDs. Keep these
    # explicit counts in the report for checkpoint and final QA evidence.
    plan: Mapping[str, str]
    vocabulary: Mapping[str, Mapping[str, str]]
    try:
        plan, vocabulary = _resolve_plan_and_vocabulary(
            model.article_id, plan_or_source, vocabulary_by_id
        )
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"{model.article_id}: cannot resolve protected plan: {exc}")
        plan = {}
        vocabulary = {}

    occurrences: tuple[CoverageOccurrence, ...] = ()
    if plan:
        _check_plan_metadata(model, plan, errors)
        try:
            occurrences = generate_coverage_occurrences(model, plan, vocabulary)
        except (KeyError, MatchingError, TypeError, ValueError) as exc:
            errors.append(f"{model.article_id}: cannot generate coverage: {exc}")
        else:
            errors.extend(_coverage_errors(model.article_id, occurrences))

    return ChapterValidationReport(
        chapter_id=model.article_id,
        word_count=word_count,
        paragraph_count=len(model.english_paragraphs),
        exercise_count=len(model.exercises),
        answer_count=len(model.answers),
        coverage_occurrences=occurrences,
        errors=tuple(errors),
    )


def validate_chapter(
    chapter: Chapter | Mapping[str, object],
    plan_or_source: Mapping[str, str] | ProtectedSourceData,
    vocabulary_by_id: Mapping[str, Mapping[str, str]] | None = None,
    *,
    min_words: int = MIN_ENGLISH_WORDS,
    max_words: int = MAX_ENGLISH_WORDS,
) -> ChapterValidationReport:
    """Validate one chapter, raising with the complete deterministic report."""

    report = check_chapter(
        chapter,
        plan_or_source,
        vocabulary_by_id,
        min_words=min_words,
        max_words=max_words,
    )
    if report.errors:
        raise ChapterValidationError(report.errors, report)
    return report


class ChapterValidator:
    """Reusable validator bound to one integrity-checked source-data snapshot."""

    def __init__(
        self,
        source_data: ProtectedSourceData,
        *,
        min_words: int = MIN_ENGLISH_WORDS,
        max_words: int = MAX_ENGLISH_WORDS,
    ) -> None:
        if not isinstance(source_data, ProtectedSourceData):
            raise TypeError("source_data must be ProtectedSourceData")
        if min_words < 0 or max_words < min_words:
            raise ValueError("word-count bounds are invalid")
        self.source_data = source_data
        self.min_words = min_words
        self.max_words = max_words

    def check(
        self, chapter: Chapter | Mapping[str, object]
    ) -> ChapterValidationReport:
        return check_chapter(
            chapter,
            self.source_data,
            min_words=self.min_words,
            max_words=self.max_words,
        )

    def validate(
        self, chapter: Chapter | Mapping[str, object]
    ) -> ChapterValidationReport:
        return validate_chapter(
            chapter,
            self.source_data,
            min_words=self.min_words,
            max_words=self.max_words,
        )


# Discoverable aliases for downstream batch and report modules.
ValidationError = ChapterValidationError
validate_chapter_against_plan = validate_chapter

__all__ = [
    "EXERCISE_COUNT",
    "MAX_ENGLISH_WORDS",
    "MAX_PARAGRAPHS",
    "MIN_ENGLISH_WORDS",
    "MIN_PARAGRAPHS",
    "ChapterValidationError",
    "ChapterValidationReport",
    "ChapterValidator",
    "ValidationError",
    "check_chapter",
    "count_english_words",
    "generate_coverage_occurrences",
    "validate_chapter",
    "validate_chapter_against_plan",
]
