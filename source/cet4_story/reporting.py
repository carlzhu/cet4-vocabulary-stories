"""Assemble the finished curriculum into auditable reports.

This module turns the committed batches into the deliverables the spec requires:

* ``vocabulary_coverage.csv`` - one row per one of the 6,127 planned targets,
  carrying the evidence that the target appears as a whole word in the English
  story of the chapter it was allocated to;
* the assembled bilingual manuscript, as editable Markdown;
* a machine-readable QA summary covering every programmatic acceptance check
  that does not need a PDF reader.

Nothing here decides that a chapter is acceptable: each chapter is re-checked
through the same validator the batch pipeline uses, so a report can never claim
coverage that ``validate-batch`` would reject.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from cet4_story.pdf_builder import select_chapters
from cet4_story.project_data import CURRICULUM_CHAPTERS, TARGET_FORMS, ProjectData, load_project

COVERAGE_CSV_PATH = Path("vocabulary_coverage.csv")
MANUSCRIPT_PATH = Path("reports") / "manuscript.md"
QA_SUMMARY_PATH = Path("reports") / "qa_summary.json"

# Calibrated from this corpus: a faithful Chinese rendering runs at a median of
# 1.48 CJK characters per English word (25th percentile 1.36). Below 1.2 the
# paragraph is a summary, not a translation.
THIN_CHINESE_DENSITY = 1.2
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

COVERAGE_FIELDS = (
    "vocabulary_id",
    "lemma",
    "part_of_speech",
    "part_of_speech_source",
    "phonetic",
    "needs_review",
    "chapter_id",
    "occurrence_count",
    "status",
    "matched_form",
    "match_method",
    "context_sentence",
)


class AuditError(ValueError):
    """The assembled curriculum failed a programmatic acceptance check."""


@dataclass(slots=True)
class CurriculumAudit:
    """Deterministic acceptance evidence for the whole curriculum."""

    chapter_ids: tuple[str, ...]
    coverage_rows: tuple[dict[str, Any], ...]
    review_rows: tuple[dict[str, Any], ...]
    problems: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_count": len(self.chapter_ids),
            "counts": dict(self.counts),
            "problems": list(self.problems),
        }


def _require(condition: bool, message: str, problems: list[str]) -> None:
    if not condition:
        problems.append(message)


def _sentence_count(text: str, chinese: bool) -> int:
    """Count sentences, tolerating the punctuation each language uses."""

    pattern = (
        r"[^。！？；…]+[。！？；…]+|[^。！？；…]+$"
        if chinese
        else r"[^.!?]+[.!?]+|[^.!?]+$"
    )
    return sum(1 for piece in re.findall(pattern, text) if piece.strip())


def _translation_counts(chapters: Iterable[Any]) -> dict[str, int]:
    """Measure whether the Chinese actually renders the English.

    The spec requires "one accurate Chinese paragraph per English paragraph". Two
    proxies are reported because neither alone is sufficient:

    * ``untranslated_english_sentences`` counts sentences past the end of the
      Chinese. It is a *lower bound*: a Chinese paragraph can skip English
      sentences in the middle and still end on the same tail.
    * ``thin_chinese_paragraphs`` counts paragraphs whose density (CJK characters
      per English word) falls below 1.2. Calibrated against this corpus, a faithful
      rendering sits at a median of 1.48 (25th percentile 1.36), so anything under
      1.2 is a summary rather than a translation.

    A gap of one sentence is not counted as untranslated: Chinese merges clauses
    that English separates with a colon or semicolon.
    """

    untranslated = 0
    short_paragraphs = 0
    thin = 0
    for chapter in chapters:
        for english, chinese in zip(chapter.english_paragraphs, chapter.chinese_paragraphs):
            gap = _sentence_count(english, False) - _sentence_count(chinese, True)
            if gap >= 2:
                untranslated += gap
                short_paragraphs += 1
            words = len(english.split())
            if words:
                density = len(_CJK.findall(chinese)) / words
                if density < THIN_CHINESE_DENSITY:
                    thin += 1
    return {
        "untranslated_english_sentences": untranslated,
        "paragraphs_with_untranslated_text": short_paragraphs,
        "thin_chinese_paragraphs": thin,
    }


def _human_review_counts(project: ProjectData, target_ids: Iterable[str]) -> dict[str, int]:
    """Count the items that still require human semantic review.

    These are reported, never hidden: they limit what the automated pipeline can
    honestly claim.
    """

    unresolved_pos = 0
    missing_phonetic = 0
    flagged = 0
    for vocabulary_id in target_ids:
        word = project.vocabulary_by_id.get(vocabulary_id) or {}
        if not (
            (word.get("part_of_speech") or "").strip()
            or (word.get("inferred_part_of_speech") or "").strip()
            or (word.get("ecdict_pos") or "").strip()
        ):
            unresolved_pos += 1
        if not (word.get("phonetic") or "").strip():
            missing_phonetic += 1
        if (word.get("needs_review") or "").strip().lower() in {"yes", "true", "1"}:
            flagged += 1
    return {
        "unresolved_part_of_speech": unresolved_pos,
        "missing_phonetic": missing_phonetic,
        "flagged_needs_review": flagged,
    }


def audit_curriculum(root: str | Path) -> CurriculumAudit:
    """Re-validate every chapter and build one coverage row per planned target."""

    project = load_project(root)
    chapters = select_chapters(root, "completed")
    validator = project.validator()

    problems: list[str] = []
    seen_ids: list[str] = []
    coverage_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    verified_new = 0
    needs_revision = 0

    expected_ids = [f"CH{number:03d}" for number in range(1, CURRICULUM_CHAPTERS + 1)]

    for chapter in chapters:
        chapter_id = chapter.article_id
        if chapter_id in seen_ids:
            problems.append(f"{chapter_id}: duplicated chapter id on disk")
        seen_ids.append(chapter_id)

        # Structural checks that do not depend on the vocabulary plan.
        _require(
            len(chapter.english_paragraphs) == len(chapter.chinese_paragraphs),
            f"{chapter_id}: English and Chinese paragraph counts differ",
            problems,
        )
        _require(
            4 <= len(chapter.english_paragraphs) <= 6,
            f"{chapter_id}: expected 4-6 paragraphs, found {len(chapter.english_paragraphs)}",
            problems,
        )
        _require(
            all(text.strip() for text in chapter.english_paragraphs),
            f"{chapter_id}: an English paragraph is empty",
            problems,
        )
        _require(
            all(text.strip() for text in chapter.chinese_paragraphs),
            f"{chapter_id}: a Chinese paragraph is empty",
            problems,
        )
        _require(
            len(chapter.exercises) == 5,
            f"{chapter_id}: expected 5 exercises, found {len(chapter.exercises)}",
            problems,
        )
        _require(
            len(chapter.answers) == 5,
            f"{chapter_id}: expected 5 answers, found {len(chapter.answers)}",
            problems,
        )
        expected_exercise_ids = [f"{chapter_id}-Q{number}" for number in range(1, 6)]
        _require(
            [item.id for item in chapter.exercises] == expected_exercise_ids,
            f"{chapter_id}: exercise ids are not CHxxx-Q1..Q5",
            problems,
        )
        _require(
            [item.id for item in chapter.answers] == expected_exercise_ids,
            f"{chapter_id}: answer ids do not match the exercise ids",
            problems,
        )

        report = validator.check(chapter)
        if not report.is_valid:
            for error in report.errors:
                problems.append(f"{chapter_id}: {error}")

        for occurrence in report.coverage_occurrences:
            row = _coverage_row(occurrence, project)
            if occurrence.kind == "new":
                coverage_rows.append(row)
                if occurrence.status == "verified":
                    verified_new += 1
                else:
                    needs_revision += 1
            else:
                review_rows.append(row)

    _require(
        seen_ids == expected_ids,
        "chapter ids on disk are not 137 unique consecutive CH001..CH137",
        problems,
    )

    allocated = sum(len(ids) for ids in project.source.new_vocabulary_ids_by_chapter.values())
    _require(allocated == TARGET_FORMS, f"planned targets {allocated} != {TARGET_FORMS}", problems)
    plan_target_ids = [
        vocabulary_id
        for ids in project.source.new_vocabulary_ids_by_chapter.values()
        for vocabulary_id in ids
    ]
    _require(
        len(set(plan_target_ids)) == len(plan_target_ids),
        "a planned target is allocated to more than one chapter",
        problems,
    )
    _require(
        len(coverage_rows) == len(plan_target_ids),
        f"coverage rows {len(coverage_rows)} != planned targets {len(plan_target_ids)}",
        problems,
    )
    _require(
        len(plan_target_ids) == TARGET_FORMS,
        f"planned target rows {len(plan_target_ids)} != {TARGET_FORMS}",
        problems,
    )
    _require(verified_new == TARGET_FORMS, f"verified new targets {verified_new} != {TARGET_FORMS}", problems)

    counts = {
        "chapters": len(seen_ids),
        "planned_targets": len(plan_target_ids),
        "verified_new": verified_new,
        "needs_revision": needs_revision,
        "uncovered": len(plan_target_ids) - len(coverage_rows),
        "review_occurrences": len(review_rows),
        "review_verified": sum(1 for row in review_rows if row["status"] == "verified"),
    }
    counts.update(_human_review_counts(project, plan_target_ids))
    counts.update(_translation_counts(chapters))
    return CurriculumAudit(
        chapter_ids=tuple(seen_ids),
        coverage_rows=tuple(coverage_rows),
        review_rows=tuple(review_rows),
        problems=tuple(problems),
        counts=counts,
    )


def _vocabulary_id(project: ProjectData, chapter_id: str) -> str:
    ids = project.source.new_vocabulary_ids_by_chapter.get(chapter_id, ())
    return ids[0] if ids else ""


def _coverage_row(occurrence: Any, project: ProjectData) -> dict[str, Any]:
    """Describe one planned occurrence for the coverage CSV.

    ``part_of_speech_source`` records where the part of speech came from, so an
    unresolved item can never be mistaken for a resolved one: ``protected`` is a
    value from the protected CSV, ``inferred`` came from the morphological
    fallback, ``ecdict`` came from ECDICT, and ``missing`` means none of them
    supplied a value and human review is still owed.
    """

    word: Mapping[str, str] = project.vocabulary_by_id.get(occurrence.vocabulary_id) or {}

    protected_pos = (word.get("part_of_speech") or "").strip()
    inferred_pos = (word.get("inferred_part_of_speech") or "").strip()
    ecdict_pos = (word.get("ecdict_pos") or "").strip()
    if protected_pos:
        pos, pos_source = protected_pos, "protected"
    elif inferred_pos:
        pos, pos_source = inferred_pos, "inferred"
    elif ecdict_pos:
        pos, pos_source = ecdict_pos, "ecdict"
    else:
        pos, pos_source = "", "missing"

    return {
        "vocabulary_id": occurrence.vocabulary_id,
        "lemma": occurrence.lemma,
        "part_of_speech": pos,
        "part_of_speech_source": pos_source,
        "phonetic": (word.get("phonetic") or "").strip(),
        "needs_review": (word.get("needs_review") or "").strip(),
        "chapter_id": occurrence.article_id,
        "occurrence_count": occurrence.occurrence_count,
        "status": occurrence.status,
        "matched_form": occurrence.matched_form or "",
        "match_method": occurrence.match_method or "",
        "context_sentence": (occurrence.context_sentence or "").replace("\n", " ").strip(),
    }


def write_coverage_csv(
    audit: CurriculumAudit,
    destination: str | Path,
) -> Path:
    """Write ``vocabulary_coverage.csv`` sorted by chapter then lemma."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(audit.coverage_rows, key=lambda row: (row["chapter_id"], row["lemma"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COVERAGE_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_manuscript(root: str | Path) -> str:
    """Render the assembled bilingual manuscript as Markdown."""

    chapters = select_chapters(root, "completed")
    lines: list[str] = [
        "# CET-4 Vocabulary Stories - assembled manuscript",
        "",
        f"- chapters: {len(chapters)}",
        "- each chapter carries its English story, its Chinese translation,",
        "  five exercises, and five answer records with explanations.",
        "",
    ]
    for chapter in chapters:
        lines.append(f"## {chapter.article_id} - {chapter.english_title} / {chapter.chinese_title}")
        lines.append("")
        lines.append(f"- theme: {chapter.theme}")
        lines.append("")
        for index, english in enumerate(chapter.english_paragraphs, start=1):
            lines.append(f"**{index}.** {english}")
            lines.append("")
            lines.append(f"{chapter.chinese_paragraphs[index - 1]}")
            lines.append("")
        lines.append("### Exercises")
        lines.append("")
        for exercise in chapter.exercises:
            options = " / ".join(exercise.options)
            lines.append(f"- {exercise.id} [{exercise.type}] {exercise.prompt}")
            if options:
                lines.append(f"  - options: {options}")
        lines.append("")
        lines.append("### Answers")
        lines.append("")
        for answer in chapter.answers:
            lines.append(f"- {answer.id}: {answer.answer} - {answer.explanation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_manuscript(root: str | Path, destination: str | Path | None = None) -> Path:
    """Write the assembled manuscript and return its path."""

    project_root = Path(root).resolve()
    path = Path(destination) if destination is not None else project_root / MANUSCRIPT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_manuscript(project_root), encoding="utf-8")
    return path


def write_qa_summary(
    audit: CurriculumAudit,
    destination: str | Path,
    *,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write the machine-readable QA summary."""

    payload: dict[str, Any] = audit.to_dict()
    if extra:
        payload.update(extra)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def review_rows_as_dicts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility helper for callers that want plain dictionaries."""

    return [dict(row) for row in rows]
