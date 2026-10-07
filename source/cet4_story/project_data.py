"""Project-level wiring between the protected sources and the ECDICT metadata.

The protected CSV sources intentionally carry no ECDICT inflections, while the
auditable ``ecdict_exchange`` values live in ``data/cet4_metadata_subset.jsonl``.
This module joins the two in memory, never rewriting a protected file, and
builds the source-provenance manifest that :mod:`cet4_story.source_data`
verifies against before any curriculum work happens.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from cet4_story.source_data import (
    PROTECTED_SOURCE_NAMES,
    ProtectedSourceData,
    SourceFormatError,
    load_source_data,
)
from cet4_story.validation import (
    MAX_ENGLISH_WORDS,
    MIN_ENGLISH_WORDS,
    ChapterValidationError,
    ChapterValidationReport,
    ChapterValidator,
    check_chapter,
)

METADATA_SUBSET_PATH = Path("data") / "cet4_metadata_subset.jsonl"
PROVENANCE_PATH = Path("reports") / "source_provenance.json"
PROVENANCE_SCHEMA_VERSION = 1

# Invariants fixed by the verified starting state of the project.
TARGET_FORMS = 6127
CURRICULUM_CHAPTERS = 137
REVIEW_EVENTS = 36762

METADATA_FIELDS = ("exchange", "pos", "phonetic", "translation", "definition")


def sha256_bytes(raw: bytes) -> str:
    """Return the lowercase SHA-256 digest of ``raw``."""

    return hashlib.sha256(raw).hexdigest()


def count_csv_records(raw: bytes) -> int:
    """Count data rows in a CSV payload, excluding the header and blank rows."""

    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = sum(1 for row in reader if any(field.strip() for field in row))
    return max(rows - 1, 0)


def build_provenance_document(root: str | Path) -> dict[str, Any]:
    """Describe every protected source with its hash and record count."""

    project_root = Path(root).resolve()
    sources: dict[str, Any] = {}
    for name in PROTECTED_SOURCE_NAMES:
        path = project_root / name
        raw = path.read_bytes()
        entry: dict[str, Any] = {"sha256": sha256_bytes(raw)}
        if path.suffix.casefold() == ".csv":
            entry["record_count"] = count_csv_records(raw)
        sources[name] = entry
    return {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
    }


def write_provenance(
    root: str | Path, destination: str | Path | None = None
) -> Path:
    """Record the current protected-source hashes and return the written path."""

    project_root = Path(root).resolve()
    target = Path(destination) if destination is not None else project_root / PROVENANCE_PATH
    document = build_provenance_document(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_metadata_subset(root: str | Path) -> Mapping[str, Mapping[str, str]]:
    """Index ``data/cet4_metadata_subset.jsonl`` by case-folded ECDICT word."""

    path = Path(root).resolve() / METADATA_SUBSET_PATH
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise SourceFormatError(f"missing metadata subset: {path}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"metadata subset is not UTF-8: {path}") from exc

    index: dict[str, dict[str, str]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourceFormatError(f"{path}:{number}: invalid JSON: {exc}") from exc
        record = payload.get("record") if isinstance(payload, dict) else None
        if not isinstance(record, Mapping):
            raise SourceFormatError(f"{path}:{number}: record must be an object")
        word = record.get("word", payload.get("word"))
        if not isinstance(word, str) or not word.strip():
            raise SourceFormatError(f"{path}:{number}: record has no word")
        key = word.strip().casefold()
        if key in index:
            raise SourceFormatError(f"{path}:{number}: duplicate metadata for {word!r}")
        index[key] = {
            field: str(record.get(field, "") or "") for field in METADATA_FIELDS
        }
    if not index:
        raise SourceFormatError(f"metadata subset is empty: {path}")
    return MappingProxyType({key: MappingProxyType(value) for key, value in index.items()})


def enrich_vocabulary(
    source: ProtectedSourceData,
    metadata: Mapping[str, Mapping[str, str]],
) -> Mapping[str, Mapping[str, str]]:
    """Return the protected vocabulary rows with auditable ECDICT fields added.

    Only ``ecdict_*``/``phonetic``/``translation`` keys are added; the protected
    columns themselves are copied unchanged.
    """

    enriched: dict[str, Mapping[str, str]] = {}
    matched = 0
    for vocabulary_id, row in source.vocabulary_by_id.items():
        record = dict(row)
        lemma = row.get("lemma", "").strip()
        meta = metadata.get(lemma.casefold())
        if meta is not None:
            matched += 1
            record["ecdict_exchange"] = meta.get("exchange", "")
            record["ecdict_pos"] = meta.get("pos", "")
            record["phonetic"] = meta.get("phonetic", "")
            record["translation"] = meta.get("translation", "")
            record["definition"] = meta.get("definition", "")
        else:
            record["ecdict_exchange"] = ""
        enriched[vocabulary_id] = MappingProxyType(record)
    if matched == 0:
        raise SourceFormatError("no vocabulary row matched the ECDICT metadata subset")
    return MappingProxyType(enriched)


@dataclass(frozen=True, slots=True)
class ProjectData:
    """One integrity-checked view of the whole project input set."""

    root: Path
    source: ProtectedSourceData
    vocabulary_by_id: Mapping[str, Mapping[str, str]]
    metadata: Mapping[str, Mapping[str, str]]
    provenance_path: Path

    @property
    def chapter_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.source.chapters_by_id))

    @property
    def metadata_match_count(self) -> int:
        return sum(
            1
            for row in self.vocabulary_by_id.values()
            if row.get("ecdict_exchange", "") or row.get("translation", "")
        )

    def validator(self) -> ChapterValidator:
        """Return a validator bound to the enriched vocabulary records."""

        return EnrichedChapterValidator(self.source, self.vocabulary_by_id)

    def summary(self) -> dict[str, Any]:
        return {
            "vocabulary_records": len(self.source.vocabulary_by_id),
            "chapters": len(self.source.chapters_by_id),
            "review_events": len(self.source.review_schedule),
            "metadata_records": len(self.metadata),
            "metadata_matched": self.metadata_match_count,
            "allocated_targets": sum(
                len(ids) for ids in self.source.new_vocabulary_ids_by_chapter.values()
            ),
        }


def _chapter_id(chapter: Any) -> str | None:
    if isinstance(chapter, Mapping):
        value = chapter.get("article_id")
    else:
        value = getattr(chapter, "article_id", None)
    return value if isinstance(value, str) and value else None


class EnrichedChapterValidator(ChapterValidator):
    """Chapter validator that uses the ECDICT-enriched vocabulary records.

    ``validation.check_chapter`` refuses to combine an explicit
    ``vocabulary_by_id`` with a :class:`ProtectedSourceData`, because the
    protected snapshot carries its own (inflection-free) index.  Passing the
    protected plan row together with the enriched index is the supported route.
    """

    def __init__(
        self,
        source_data: ProtectedSourceData,
        vocabulary_by_id: Mapping[str, Mapping[str, str]],
        *,
        min_words: int = MIN_ENGLISH_WORDS,
        max_words: int = MAX_ENGLISH_WORDS,
    ) -> None:
        super().__init__(source_data, min_words=min_words, max_words=max_words)
        self.vocabulary_by_id = vocabulary_by_id

    def plan_row(self, chapter: Any) -> Mapping[str, str]:
        """Return the protected plan row for ``chapter``, or an empty mapping."""

        chapter_id = _chapter_id(chapter)
        if chapter_id is None:
            return {}
        try:
            return self.source_data.chapter_record(chapter_id)
        except (KeyError, TypeError, ValueError):
            return {}

    def check(self, chapter: Any) -> ChapterValidationReport:
        return check_chapter(
            chapter,
            self.plan_row(chapter),
            self.vocabulary_by_id,
            min_words=self.min_words,
            max_words=self.max_words,
        )

    def validate(self, chapter: Any) -> ChapterValidationReport:
        report = self.check(chapter)
        if report.errors:
            raise ChapterValidationError(report.errors, report)
        return report


def load_project(
    root: str | Path | None = None,
    *,
    provenance_path: str | Path | None = None,
) -> ProjectData:
    """Load protected sources, their provenance, and the ECDICT metadata subset."""

    project_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]
    report_path = (
        Path(provenance_path).resolve()
        if provenance_path is not None
        else project_root / PROVENANCE_PATH
    )
    if not report_path.is_file():
        raise SourceFormatError(
            f"missing source provenance {report_path}; run "
            "`python -c \"from cet4_story.project_data import write_provenance;"
            " write_provenance('.')\"` first"
        )
    source = load_source_data(project_root, provenance_path=report_path)
    metadata = load_metadata_subset(project_root)
    vocabulary_by_id = enrich_vocabulary(source, metadata)
    return ProjectData(
        root=project_root,
        source=source,
        vocabulary_by_id=vocabulary_by_id,
        metadata=metadata,
        provenance_path=report_path,
    )


def verify_invariants(project: ProjectData) -> dict[str, Any]:
    """Confirm the three fixed invariants and the single-assignment rule."""

    summary = project.summary()
    allocation = project.source.new_vocabulary_ids_by_chapter
    flattened = [vocabulary_id for ids in allocation.values() for vocabulary_id in ids]
    problems: list[str] = []
    if summary["vocabulary_records"] != TARGET_FORMS:
        problems.append(
            f"vocabulary records {summary['vocabulary_records']} != {TARGET_FORMS}"
        )
    if summary["chapters"] != CURRICULUM_CHAPTERS:
        problems.append(f"chapters {summary['chapters']} != {CURRICULUM_CHAPTERS}")
    if summary["review_events"] != REVIEW_EVENTS:
        problems.append(f"review events {summary['review_events']} != {REVIEW_EVENTS}")
    if len(set(flattened)) != len(flattened):
        problems.append("a target is allocated to more than one chapter")
    if set(flattened) != set(project.source.vocabulary_by_id):
        problems.append("allocation does not cover every target exactly once")
    expected_ids = [f"CH{number:03d}" for number in range(1, CURRICULUM_CHAPTERS + 1)]
    if list(project.chapter_ids) != expected_ids:
        problems.append("chapter ids are not the consecutive CH001-CH137 set")
    if problems:
        raise ValueError("; ".join(problems))
    return summary


__all__ = [
    "CURRICULUM_CHAPTERS",
    "EnrichedChapterValidator",
    "METADATA_SUBSET_PATH",
    "PROVENANCE_PATH",
    "ProjectData",
    "REVIEW_EVENTS",
    "TARGET_FORMS",
    "build_provenance_document",
    "count_csv_records",
    "enrich_vocabulary",
    "load_metadata_subset",
    "load_project",
    "sha256_bytes",
    "verify_invariants",
    "write_provenance",
]
