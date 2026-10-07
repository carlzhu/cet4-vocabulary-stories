"""Contract tests for integrity-checked curriculum source loading."""

from __future__ import annotations

import csv
import hashlib
from importlib import import_module
import json
from pathlib import Path
import shutil
import sys
from typing import Callable

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "source"))
source_data = import_module("cet4_story.source_data")

PROTECTED_SOURCE_NAMES = source_data.PROTECTED_SOURCE_NAMES
SourceFormatError = source_data.SourceFormatError
load_source_data = source_data.load_source_data

VOCABULARY_COUNT = 6_127
CHAPTER_COUNT = 137
REVIEW_EVENT_COUNT = 36_762

FIRST_VOCABULARY_ROW = {
    "vocabulary_id": "V0001",
    "word": "abandon",
    "phonetic": "ə'bændən",
    "translation": "vt. 放弃,遗弃; n. 放任",
    "pos": "v;n",
    "collins": "3",
    "oxford": "1",
    "tag": "cet4 cet6",
    "bnc": "2451",
    "frq": "1742",
    "exchange": "d:abandoned/p:abandoned/3:abandons/i:abandoning",
    "detail": '{"source":"ECDICT","note":"comma, slash / ampersand &"}',
    "audio": "",
}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _vocabulary_rows() -> list[dict[str, str]]:
    rows = [FIRST_VOCABULARY_ROW.copy()]
    for number in range(2, VOCABULARY_COUNT + 1):
        rows.append(
            {
                "vocabulary_id": f"V{number:04d}",
                "word": f"word-{number}",
                "phonetic": f"phonetic-{number}",
                "translation": f"translation {number}",
                "pos": "n",
                "collins": "0",
                "oxford": "0",
                "tag": "cet4",
                "bnc": str(10_000 + number),
                "frq": str(20_000 + number),
                "exchange": "",
                "detail": "",
                "audio": "",
            }
        )
    return rows


def _plan_rows() -> tuple[list[dict[str, str]], dict[str, tuple[str, ...]]]:
    rows: list[dict[str, str]] = []
    expected_allocation: dict[str, tuple[str, ...]] = {}
    next_vocabulary = 1
    large_chapter_count = VOCABULARY_COUNT % CHAPTER_COUNT
    base_size = VOCABULARY_COUNT // CHAPTER_COUNT

    for chapter_number in range(1, CHAPTER_COUNT + 1):
        chapter_id = f"CH{chapter_number:03d}"
        size = base_size + (chapter_number <= large_chapter_count)
        allocated = tuple(
            f"V{number:04d}"
            for number in range(next_vocabulary, next_vocabulary + size)
        )
        next_vocabulary += size
        expected_allocation[chapter_id] = allocated
        rows.append(
            {
                "chapter_id": chapter_id,
                "title": f"Exact title {chapter_number}",
                "theme": f"Theme {chapter_number}",
                "plot_summary": f"Plot summary, chapter {chapter_number}.",
                "new_vocabulary_ids": json.dumps(
                    allocated, ensure_ascii=False, separators=(",", ":")
                ),
                "review_vocabulary_ids": "[]",
            }
        )

    assert next_vocabulary == VOCABULARY_COUNT + 1
    return rows, expected_allocation


def _review_rows(
    expected_allocation: dict[str, tuple[str, ...]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    offsets = (1, 3, 7, 14, 30, 60)
    source_by_id = {
        vocabulary_id: chapter_id
        for chapter_id, vocabulary_ids in expected_allocation.items()
        for vocabulary_id in vocabulary_ids
    }
    for vocabulary_number in range(1, VOCABULARY_COUNT + 1):
        vocabulary_id = f"V{vocabulary_number:04d}"
        source_chapter = source_by_id[vocabulary_id]
        source_number = int(source_chapter[2:])
        for review_number, offset in enumerate(offsets, start=1):
            rows.append(
                {
                    "vocabulary_id": vocabulary_id,
                    "source_chapter_id": source_chapter,
                    "review_chapter_id": f"CH{min(CHAPTER_COUNT, source_number + offset):03d}",
                    "review_number": str(review_number),
                }
            )
    assert len(rows) == REVIEW_EVENT_COUNT
    return rows


def _rewrite_provenance(root: Path) -> None:
    record_counts = {
        "vocabulary_master.csv": VOCABULARY_COUNT,
        "curriculum_plan.csv": CHAPTER_COUNT,
        "review_schedule.csv": REVIEW_EVENT_COUNT,
    }
    sources: dict[str, dict[str, str | int]] = {}
    for name in PROTECTED_SOURCE_NAMES:
        raw = (root / name).read_bytes()
        record: dict[str, str | int] = {
            "sha256": hashlib.sha256(raw).hexdigest()
        }
        if name in record_counts:
            record["record_count"] = record_counts[name]
        sources[name] = record

    report_path = root / "reports" / "source_provenance.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"schema_version": 1, "sources": sources}, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_verified_source_tree(root: Path) -> dict[str, tuple[str, ...]]:
    vocabulary_rows = _vocabulary_rows()
    plan_rows, expected_allocation = _plan_rows()
    review_rows = _review_rows(expected_allocation)

    _write_csv(root / "vocabulary_master.csv", list(vocabulary_rows[0]), vocabulary_rows)
    _write_csv(root / "curriculum_plan.csv", list(plan_rows[0]), plan_rows)
    _write_csv(root / "review_schedule.csv", list(review_rows[0]), review_rows)
    (root / "character_guide.md").write_bytes(
        b"# Character Guide\n\nExact character facts.\n"
    )
    (root / "story_timeline.md").write_bytes(
        b"# Story Timeline\n\nExact timeline facts.\n"
    )
    _rewrite_provenance(root)
    return expected_allocation


@pytest.fixture(scope="module")
def verified_source_tree(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, tuple[str, ...]]]:
    root = tmp_path_factory.mktemp("verified-sources")
    return root, _build_verified_source_tree(root)


def test_verified_counts_chapter_sequence_and_unique_allocation(
    verified_source_tree: tuple[Path, dict[str, tuple[str, ...]]],
) -> None:
    root, expected_allocation = verified_source_tree
    loaded = load_source_data(root)

    assert len(loaded.vocabulary_master) == VOCABULARY_COUNT
    assert len(loaded.curriculum_plan) == CHAPTER_COUNT
    assert len(loaded.review_schedule) == REVIEW_EVENT_COUNT
    assert tuple(loaded.chapters_by_id) == tuple(
        f"CH{number:03d}" for number in range(1, CHAPTER_COUNT + 1)
    )
    assert dict(loaded.new_vocabulary_ids_by_chapter) == expected_allocation

    assigned = [
        vocabulary_id
        for chapter_ids in loaded.new_vocabulary_ids_by_chapter.values()
        for vocabulary_id in chapter_ids
    ]
    assert len(assigned) == VOCABULARY_COUNT
    assert len(set(assigned)) == VOCABULARY_COUNT
    assert set(assigned) == set(loaded.vocabulary_by_id)


def test_exact_source_metadata_is_retained(
    verified_source_tree: tuple[Path, dict[str, tuple[str, ...]]],
) -> None:
    root, _ = verified_source_tree
    loaded = load_source_data(root)

    assert dict(loaded.vocabulary_record("V0001")) == FIRST_VOCABULARY_ROW
    assert dict(loaded.chapter_record("CH001")) == {
        "chapter_id": "CH001",
        "title": "Exact title 1",
        "theme": "Theme 1",
        "plot_summary": "Plot summary, chapter 1.",
        "new_vocabulary_ids": json.dumps(
            loaded.new_vocabulary_ids_by_chapter["CH001"],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "review_vocabulary_ids": "[]",
    }
    assert loaded.character_guide == "# Character Guide\n\nExact character facts.\n"
    assert loaded.story_timeline == "# Story Timeline\n\nExact timeline facts.\n"
    with pytest.raises(TypeError):
        loaded.vocabulary_record("V0001")["word"] = "changed"


def _alter_vocabulary_id(root: Path) -> None:
    path = root / "vocabulary_master.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["vocabulary_id"] = "V9999"
    _write_csv(path, list(rows[0]), rows)


def _alter_allocation(root: Path) -> None:
    path = root / "curriculum_plan.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    second_chapter_ids = json.loads(rows[1]["new_vocabulary_ids"])
    second_chapter_ids[0] = "V0001"
    rows[1]["new_vocabulary_ids"] = json.dumps(
        second_chapter_ids, separators=(",", ":")
    )
    _write_csv(path, list(rows[0]), rows)


@pytest.mark.parametrize(
    "alter_source",
    [_alter_vocabulary_id, _alter_allocation],
    ids=["altered-vocabulary-id", "altered-allocation"],
)
def test_semantically_altered_ids_or_allocations_are_rejected(
    tmp_path: Path,
    verified_source_tree: tuple[Path, dict[str, tuple[str, ...]]],
    alter_source: Callable[[Path], None],
) -> None:
    verified_root, _ = verified_source_tree
    root = tmp_path / "altered-sources"
    shutil.copytree(verified_root, root)
    alter_source(root)
    _rewrite_provenance(root)

    with pytest.raises(SourceFormatError):
        load_source_data(root)
