from __future__ import annotations

import csv
from pathlib import Path

from cet4_story.vocabulary import comparison_key, import_vocabulary, normalize_text


def test_normalize_text() -> None:
    assert normalize_text("  ＡＢＣ\u00a0 word  ") == "ABC word"
    assert comparison_key("Ability") == "ability"


def test_import_preserves_raw_and_separates_senses(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text(
        "word,pos,meaning\n"
        "present,n.,礼物\n"
        "Present,n.,礼物\n"
        "present,v.,呈现\n"
        "ability,n.,能力\n",
        encoding="utf-8",
    )

    audit = import_vocabulary(source, tmp_path)

    assert audit["raw_records"] == 4
    assert audit["unique_targets"] == 3
    assert audit["exact_duplicate_rows"] == 1
    assert audit["needs_review"] == 2

    with (tmp_path / "vocabulary_master.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert sum(row["lemma"].casefold() == "present" for row in rows) == 2
    assert all(row["vocabulary_id"].startswith("cet4-") for row in rows)
