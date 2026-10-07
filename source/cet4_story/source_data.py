"""Integrity-checked access to the immutable curriculum source data.

All protected files are hashed before they are parsed.  CSV values are retained
exactly as decoded (including ECDICT metadata); normalized values are used only
for validation and indexes.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence, TypeAlias

CsvRow: TypeAlias = Mapping[str, str]

PROTECTED_SOURCE_NAMES = (
    "vocabulary_master.csv",
    "curriculum_plan.csv",
    "review_schedule.csv",
    "character_guide.md",
    "story_timeline.md",
)
CSV_SOURCE_NAMES = PROTECTED_SOURCE_NAMES[:3]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHAPTER_ID = re.compile(r"^CH(\d{3})$")


class SourceDataError(ValueError):
    """Base exception for invalid or unavailable protected source data."""


class SourceIntegrityError(SourceDataError):
    """A protected file does not match its recorded provenance."""


class SourceFormatError(SourceDataError):
    """A source or provenance document has an invalid structure."""


@dataclass(frozen=True, slots=True)
class SourceFileProvenance:
    """The immutable facts used to verify one protected source file."""

    name: str
    sha256: str
    record_count: int | None = None

    def __post_init__(self) -> None:
        if self.name not in PROTECTED_SOURCE_NAMES:
            raise SourceFormatError(f"unexpected protected source: {self.name!r}")
        if not _SHA256.fullmatch(self.sha256):
            raise SourceFormatError(f"invalid SHA-256 for {self.name}: {self.sha256!r}")
        if self.record_count is not None and self.record_count < 0:
            raise SourceFormatError(f"negative record count for {self.name}")


@dataclass(frozen=True, slots=True)
class ProtectedSourceData:
    """Verified source records plus immutable indexes for downstream tools."""

    project_root: Path
    provenance: Mapping[str, SourceFileProvenance]
    vocabulary: tuple[CsvRow, ...]
    curriculum_plan: tuple[CsvRow, ...]
    review_schedule: tuple[CsvRow, ...]
    character_guide: str
    story_timeline: str
    vocabulary_id_field: str
    chapter_id_field: str
    vocabulary_by_id: Mapping[str, CsvRow]
    chapters_by_id: Mapping[str, CsvRow]
    new_vocabulary_ids_by_chapter: Mapping[str, tuple[str, ...]]

    @property
    def vocabulary_master(self) -> tuple[CsvRow, ...]:
        """Compatibility alias matching the protected CSV file name."""

        return self.vocabulary

    @property
    def curriculum_by_chapter(self) -> Mapping[str, CsvRow]:
        return self.chapters_by_id

    @property
    def source_hashes(self) -> Mapping[str, str]:
        return MappingProxyType(
            {name: item.sha256 for name, item in self.provenance.items()}
        )

    def vocabulary_record(self, vocabulary_id: str) -> CsvRow:
        try:
            return self.vocabulary_by_id[vocabulary_id]
        except KeyError as exc:
            raise KeyError(f"unknown vocabulary id: {vocabulary_id!r}") from exc

    def chapter_record(self, chapter_id: str) -> CsvRow:
        try:
            return self.chapters_by_id[chapter_id]
        except KeyError as exc:
            raise KeyError(f"unknown chapter id: {chapter_id!r}") from exc


# Accepted aliases are intentionally narrow: values are never renamed or
# rewritten, but established source-file variants can still be validated.
_VOCABULARY_ID_FIELDS = ("vocabulary_id", "word_id", "vocab_id", "id")
_CHAPTER_ID_FIELDS = ("chapter_id", "article_id")
_NEW_IDS_FIELDS = (
    "new_vocabulary_ids",
    "new_vocab_ids",
    "new_word_ids",
    "assigned_vocabulary_ids",
)
_SINGLE_NEW_ID_FIELDS = ("vocabulary_id", "vocab_id", "word_id")
_COUNT_FIELDS = ("record_count", "row_count", "rows", "count")
_HASH_FIELDS = ("sha256", "sha_256", "hash")


def _project_root(value: str | Path | None) -> Path:
    if value is None:
        return Path(__file__).resolve().parents[2]
    return Path(value).expanduser().resolve()


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise SourceIntegrityError(f"protected source is missing: {path}") from exc
    except OSError as exc:
        raise SourceIntegrityError(f"cannot read protected source {path}: {exc}") from exc


def _decode_utf8(raw: bytes, path: Path) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SourceFormatError(f"{path} is not valid UTF-8: {exc}") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _entry_name(entry: Mapping[str, Any], fallback: str | None) -> str:
    candidate = entry.get("name", entry.get("path", entry.get("file", fallback)))
    if not isinstance(candidate, str) or not candidate:
        raise SourceFormatError("provenance source entry is missing a file name")
    return Path(candidate.replace("\\", "/")).name


def _integer_count(entry: Mapping[str, Any], name: str) -> int | None:
    for field in _COUNT_FIELDS:
        if field not in entry:
            continue
        value = entry[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise SourceFormatError(f"{field} for {name} must be an integer")
        return value
    return None


def _provenance_entries(document: object) -> Iterable[tuple[str | None, Mapping[str, Any]]]:
    if not isinstance(document, Mapping):
        raise SourceFormatError("source provenance must be a JSON object")

    container: object = document.get("sources", document.get("files"))
    if container is None:
        container = {
            key: value
            for key, value in document.items()
            if Path(str(key).replace("\\", "/")).name in PROTECTED_SOURCE_NAMES
        }

    if isinstance(container, Mapping):
        for key, value in container.items():
            if isinstance(value, str):
                yield str(key), {"sha256": value}
            elif isinstance(value, Mapping):
                yield str(key), value
            else:
                raise SourceFormatError(f"invalid provenance entry for {key!r}")
        return

    if isinstance(container, Sequence) and not isinstance(container, (str, bytes)):
        for value in container:
            if not isinstance(value, Mapping):
                raise SourceFormatError("provenance source list contains a non-object")
            yield None, value
        return

    raise SourceFormatError("provenance must contain a sources/files object or array")


def load_provenance(path: str | Path) -> Mapping[str, SourceFileProvenance]:
    """Load and strictly normalize the five protected-source declarations."""

    provenance_path = Path(path)
    raw = _read_bytes(provenance_path)
    try:
        document = json.loads(_decode_utf8(raw, provenance_path))
    except json.JSONDecodeError as exc:
        raise SourceFormatError(f"invalid provenance JSON {provenance_path}: {exc}") from exc

    records: dict[str, SourceFileProvenance] = {}
    for fallback, entry in _provenance_entries(document):
        name = _entry_name(entry, fallback)
        if name not in PROTECTED_SOURCE_NAMES:
            continue
        digest: object = None
        for field in _HASH_FIELDS:
            if field in entry:
                digest = entry[field]
                break
        if not isinstance(digest, str):
            raise SourceFormatError(f"provenance for {name} is missing sha256")
        if name in records:
            raise SourceFormatError(f"duplicate provenance entry for {name}")
        records[name] = SourceFileProvenance(
            name=name,
            sha256=digest.lower(),
            record_count=_integer_count(entry, name),
        )

    missing = sorted(set(PROTECTED_SOURCE_NAMES) - records.keys())
    if missing:
        raise SourceFormatError(
            "provenance is missing protected sources: " + ", ".join(missing)
        )
    return MappingProxyType(records)


def _parse_csv(raw: bytes, path: Path) -> tuple[CsvRow, ...]:
    text = _decode_utf8(raw, path)
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise SourceFormatError(f"{path} has no CSV header")
        if any(name is None or name == "" for name in fieldnames):
            raise SourceFormatError(f"{path} has a blank CSV header")
        if len(set(fieldnames)) != len(fieldnames):
            raise SourceFormatError(f"{path} has duplicate CSV headers")

        rows: list[CsvRow] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise SourceFormatError(f"{path}:{line_number} has extra CSV fields")
            if any(value is None for value in row.values()):
                raise SourceFormatError(f"{path}:{line_number} has missing CSV fields")
            # MappingProxyType prevents downstream code from silently changing
            # ECDICT metadata or allocation cells.
            rows.append(MappingProxyType(dict(row)))  # type: ignore[arg-type]
        return tuple(rows)
    except csv.Error as exc:
        raise SourceFormatError(f"invalid CSV in {path}: {exc}") from exc


def _field(rows: tuple[CsvRow, ...], candidates: Sequence[str], label: str) -> str:
    if not rows:
        raise SourceFormatError(f"{label} is empty")
    header = rows[0].keys()
    for candidate in candidates:
        if candidate in header:
            return candidate
    raise SourceFormatError(
        f"{label} has none of the required columns: {', '.join(candidates)}"
    )


def _unique_index(rows: tuple[CsvRow, ...], field: str, label: str) -> Mapping[str, CsvRow]:
    result: dict[str, CsvRow] = {}
    for row_number, row in enumerate(rows, start=2):
        value = row[field]
        if value == "":
            raise SourceFormatError(f"{label}:{row_number} has a blank {field}")
        if value in result:
            raise SourceFormatError(f"duplicate {field} in {label}: {value!r}")
        result[value] = row
    return MappingProxyType(result)


def _id_list(raw: str, *, chapter_id: str, field: str) -> tuple[str, ...]:
    if raw == "":
        return ()
    value = raw.strip()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SourceFormatError(
                f"invalid JSON ID list in {chapter_id}.{field}: {exc}"
            ) from exc
        if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
            raise SourceFormatError(f"{chapter_id}.{field} must be an array of strings")
        return tuple(parsed)

    for delimiter in (";", "|", ","):
        if delimiter in value:
            parts = tuple(part.strip() for part in value.split(delimiter))
            if any(not part for part in parts):
                raise SourceFormatError(f"{chapter_id}.{field} contains a blank ID")
            return parts
    return (value,)


def _validate_chapters(chapters: Mapping[str, CsvRow]) -> None:
    numbered: list[int] = []
    for chapter_id in chapters:
        match = _CHAPTER_ID.fullmatch(chapter_id)
        if match is None:
            raise SourceFormatError(f"invalid chapter id: {chapter_id!r}")
        numbered.append(int(match.group(1)))
    expected = list(range(1, len(numbered) + 1))
    if sorted(numbered) != expected:
        raise SourceFormatError("curriculum chapter IDs must be consecutive from CH001")


def _allocation(
    plan: tuple[CsvRow, ...],
    chapter_field: str,
    vocabulary_ids: set[str],
) -> Mapping[str, tuple[str, ...]]:
    header = plan[0].keys()
    list_field = next((field for field in _NEW_IDS_FIELDS if field in header), None)
    single_field = next((field for field in _SINGLE_NEW_ID_FIELDS if field in header), None)
    if list_field is None and single_field is None:
        raise SourceFormatError(
            "curriculum plan has no new-vocabulary allocation column"
        )

    allocation: dict[str, list[str]] = {}
    assigned_to: dict[str, str] = {}
    allocation_field = list_field or single_field
    assert allocation_field is not None
    for row in plan:
        chapter_id = row[chapter_field]
        ids = (
            _id_list(row[allocation_field], chapter_id=chapter_id, field=allocation_field)
            if list_field is not None
            else (row[allocation_field],)
        )
        bucket = allocation.setdefault(chapter_id, [])
        for vocabulary_id in ids:
            if vocabulary_id not in vocabulary_ids:
                raise SourceFormatError(
                    f"{chapter_id} assigns unknown vocabulary id {vocabulary_id!r}"
                )
            prior = assigned_to.get(vocabulary_id)
            if prior is not None:
                raise SourceFormatError(
                    f"vocabulary id {vocabulary_id!r} is assigned to both "
                    f"{prior} and {chapter_id}"
                )
            assigned_to[vocabulary_id] = chapter_id
            bucket.append(vocabulary_id)

    missing = sorted(vocabulary_ids - assigned_to.keys())
    if missing:
        preview = ", ".join(missing[:10])
        suffix = "..." if len(missing) > 10 else ""
        raise SourceFormatError(
            f"{len(missing)} vocabulary IDs are not allocated: {preview}{suffix}"
        )
    return MappingProxyType({key: tuple(value) for key, value in allocation.items()})


def _verify_record_count(
    provenance: SourceFileProvenance, rows: tuple[CsvRow, ...]
) -> None:
    if provenance.record_count is not None and len(rows) != provenance.record_count:
        raise SourceIntegrityError(
            f"record count mismatch for {provenance.name}: expected "
            f"{provenance.record_count}, got {len(rows)}"
        )


def load_source_data(
    project_root: str | Path | None = None,
    *,
    provenance_path: str | Path | None = None,
) -> ProtectedSourceData:
    """Load source data only after hash, count, and allocation verification.

    ``project_root`` defaults to the repository containing this module.  A
    custom ``provenance_path`` is useful for isolated tests but does not weaken
    the requirement that all five protected sources be declared and verified.
    """

    root = _project_root(project_root)
    report_path = (
        Path(provenance_path).expanduser().resolve()
        if provenance_path is not None
        else root / "reports" / "source_provenance.json"
    )
    provenance = load_provenance(report_path)

    raw_sources: dict[str, bytes] = {}
    for name in PROTECTED_SOURCE_NAMES:
        raw = _read_bytes(root / name)
        actual = _sha256(raw)
        expected = provenance[name].sha256
        if actual != expected:
            raise SourceIntegrityError(
                f"SHA-256 mismatch for {name}: expected {expected}, got {actual}"
            )
        raw_sources[name] = raw

    vocabulary = _parse_csv(raw_sources["vocabulary_master.csv"], root / "vocabulary_master.csv")
    plan = _parse_csv(raw_sources["curriculum_plan.csv"], root / "curriculum_plan.csv")
    schedule = _parse_csv(raw_sources["review_schedule.csv"], root / "review_schedule.csv")
    for name, rows in (
        ("vocabulary_master.csv", vocabulary),
        ("curriculum_plan.csv", plan),
        ("review_schedule.csv", schedule),
    ):
        _verify_record_count(provenance[name], rows)

    vocabulary_id_field = _field(
        vocabulary, _VOCABULARY_ID_FIELDS, "vocabulary_master.csv"
    )
    chapter_id_field = _field(plan, _CHAPTER_ID_FIELDS, "curriculum_plan.csv")
    vocabulary_by_id = _unique_index(
        vocabulary, vocabulary_id_field, "vocabulary_master.csv"
    )
    chapters_by_id = _unique_index(plan, chapter_id_field, "curriculum_plan.csv")
    _validate_chapters(chapters_by_id)
    allocation = _allocation(
        plan, chapter_id_field, set(vocabulary_by_id)
    )

    character_guide = _decode_utf8(
        raw_sources["character_guide.md"], root / "character_guide.md"
    )
    story_timeline = _decode_utf8(
        raw_sources["story_timeline.md"], root / "story_timeline.md"
    )
    if not character_guide.strip():
        raise SourceFormatError("character_guide.md must not be blank")
    if not story_timeline.strip():
        raise SourceFormatError("story_timeline.md must not be blank")

    return ProtectedSourceData(
        project_root=root,
        provenance=provenance,
        vocabulary=vocabulary,
        curriculum_plan=plan,
        review_schedule=schedule,
        character_guide=character_guide,
        story_timeline=story_timeline,
        vocabulary_id_field=vocabulary_id_field,
        chapter_id_field=chapter_id_field,
        vocabulary_by_id=vocabulary_by_id,
        chapters_by_id=chapters_by_id,
        new_vocabulary_ids_by_chapter=allocation,
    )


__all__ = [
    "CSV_SOURCE_NAMES",
    "PROTECTED_SOURCE_NAMES",
    "ProtectedSourceData",
    "SourceDataError",
    "SourceFileProvenance",
    "SourceFormatError",
    "SourceIntegrityError",
    "load_provenance",
    "load_source_data",
]
