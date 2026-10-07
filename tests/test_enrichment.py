from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from cet4_story import enrichment


def _write_master(path: Path, count: int = 6127) -> None:
    fields = [
        "vocabulary_id", "lemma", "part_of_speech", "chinese_meaning", "word_family",
        "status", "assigned_article", "occurrence_count", "source_file", "source_row",
        "original_lemma", "duplicate_group", "needs_review",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index in range(count):
            lemma = "ability" if index == 0 else f"word{index:04d}"
            writer.writerow({
                "vocabulary_id": f"cet4-{index:012d}",
                "lemma": lemma,
                "status": "needs_review",
                "occurrence_count": 0,
                "source_file": "fixture.json",
                "source_row": index + 1,
                "original_lemma": lemma,
                "needs_review": "yes",
            })


def test_exact_enrichment_preserves_target_count(tmp_path: Path) -> None:
    _write_master(tmp_path / "vocabulary_master.csv")
    shard = tmp_path / "0001.json"
    shard.write_text(
        json.dumps({
            "word": "Ability",
            "translation": ["能力"],
            "pos": ["n:100"],
            "phonetic": "əˈbɪləti",
            "exchange": ["s:abilities"],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = enrichment.enrich_from_shards(
        tmp_path, [shard], source_id="fixture", source_sha256="abc"
    )

    assert result["target_count"] == 6127
    assert result["exact_single_candidate"] == 1
    assert result["unmatched"] == 6126
    with (tmp_path / "vocabulary_master.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6127
    assert rows[0]["chinese_meaning"] == "能力"
    assert rows[0]["part_of_speech"] == "n:100"
    assert rows[0]["metadata_match_status"] == "exact"


def test_filter_ecdict_csv_keeps_only_exact_targets(tmp_path: Path) -> None:
    _write_master(tmp_path / "vocabulary_master.csv")
    source = tmp_path / "ecdict.csv"
    source.write_text(
        "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,"
        "exchange,detail,audio\n"
        "Ability,phon,definition,能力,n:100,5,1,cet4,10,20,s:abilities,,\n"
        "unrelated,phon,definition,无关,n:100,,,,,,,\n",
        encoding="utf-8",
    )
    output = tmp_path / "filtered.jsonl"
    counts = enrichment.filter_ecdict_csv(
        tmp_path / "vocabulary_master.csv", source, output
    )
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert counts == {"scanned_rows": 2, "matched_rows": 1}
    assert records[0]["word"] == "Ability"
    assert records[0]["_source_line"] == 2


def test_rejects_changed_target_baseline(tmp_path: Path) -> None:
    _write_master(tmp_path / "vocabulary_master.csv", count=2)
    shard = tmp_path / "0001.json"
    shard.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="6,127"):
        enrichment.enrich_from_shards(tmp_path, [shard], source_id="fixture")



def test_infer_pos_from_translation() -> None:
    value = "n. 能力；vt. 使能够；[网络] 其他释义"
    assert enrichment.infer_pos_from_translation(value) == "vt/n"
    assert enrichment.infer_pos_from_translation("没有明确词性") == ""
