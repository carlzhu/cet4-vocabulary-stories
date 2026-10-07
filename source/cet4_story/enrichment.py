from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_COMMIT = "522c17036976c34c994a1d367bd61a7d9fa495d9"
BASE_URL = "https://raw.githubusercontent.com/ismartcoding/endict/{commit}/dict/{name}.json"
EXTRA_FIELDS = [
    "phonetic",
    "english_definition",
    "ecdict_translation",
    "ecdict_pos",
    "ecdict_exchange",
    "ecdict_examples",
    "ecdict_collins",
    "ecdict_oxford",
    "ecdict_tag",
    "ecdict_bnc_frequency",
    "ecdict_contemporary_frequency",
    "ecdict_detail",
    "ecdict_audio",
    "inferred_part_of_speech",
    "pos_inference_method",
    "metadata_match_status",
    "metadata_candidate_count",
    "metadata_source",
]


@dataclass(frozen=True)
class ShardInfo:
    name: str
    path: str
    size: int
    sha256: str
    lines: int


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_one(name: str, destination: Path, commit: str, retries: int = 3) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    url = BASE_URL.format(commit=commit, name=name)
    request = urllib.request.Request(url, headers={"User-Agent": "CET4-Vocabulary-Audit/1.0"})
    last_error: Exception | None = None
    for attempt in range(retries):
        temporary = destination.with_suffix(".part")
        try:
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            if temporary.stat().st_size == 0:
                raise OSError(f"Downloaded empty shard: {name}")
            temporary.replace(destination)
            return destination
        except Exception as exc:  # network exceptions vary by platform
            last_error = exc
            temporary.unlink(missing_ok=True)
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to download shard {name} after {retries} attempts") from last_error


def download_shards(
    scratch_root: Path,
    commit: str = DEFAULT_COMMIT,
    workers: int = 8,
    shard_count: int = 608,
) -> list[Path]:
    shard_root = scratch_root / f"endict-{commit}" / "dict"
    names = [f"{index:04d}" for index in range(1, shard_count + 1)]
    results: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 12))) as executor:
        futures = {
            executor.submit(_download_one, name, shard_root / f"{name}.json", commit): name
            for name in names
        }
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()
    if len(results) != shard_count:
        raise RuntimeError(f"Expected {shard_count} shards, downloaded {len(results)}")
    return [results[name] for name in names]


def inspect_shard(path: Path) -> ShardInfo:
    with path.open("rb") as handle:
        lines = sum(1 for line in handle if line.strip())
    return ShardInfo(
        name=path.name,
        path=str(path),
        size=path.stat().st_size,
        sha256=file_sha256(path),
        lines=lines,
    )


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _join_unique(records: Iterable[dict[str, Any]], field: str) -> str:
    seen: set[str] = set()
    values: list[str] = []
    for record in records:
        for value in _as_list(record.get(field)):
            if value not in seen:
                seen.add(value)
                values.append(value)
    return " || ".join(values)


POS_ORDER = ["art", "aux", "conj", "int", "num", "prep", "pron", "abbr", "adv", "adj", "ad", "vi", "vt", "n", "v", "a"]
POS_PATTERN = re.compile(
    "(?:^|[^A-Za-z])(art|aux|conj|int|num|prep|pron|abbr|adv|adj|ad|vi|vt|n|v|a)[.]",
    re.IGNORECASE,
)


def infer_pos_from_translation(translation: str) -> str:
    found = {value.casefold() for value in POS_PATTERN.findall(translation)}
    return "/".join(value for value in POS_ORDER if value in found)


def _read_master(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _write_master(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def collect_candidates(
    targets: set[str], shard_paths: Iterable[Path]
) -> tuple[dict[str, list[dict[str, Any]]], int, list[dict[str, Any]]]:
    matches: dict[str, list[dict[str, Any]]] = {target: [] for target in targets}
    invalid_lines = 0
    matched_rows: list[dict[str, Any]] = []
    for shard_path in shard_paths:
        with shard_path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw_record = json.loads(line)
                except json.JSONDecodeError:
                    invalid_lines += 1
                    continue
                record = dict(raw_record)
                word = str(record.get("word", "")).strip()
                key = word.casefold()
                if key not in targets:
                    continue
                source_name = str(record.pop("_source_file", shard_path.name))
                source_line = int(record.pop("_source_line", line_number))
                candidate = {
                    "source_shard": source_name,
                    "source_line": source_line,
                    "word": word,
                    "record": record,
                }
                matches[key].append(candidate)
                matched_rows.append(candidate)
    return matches, invalid_lines, matched_rows


def enrich_from_shards(
    project_root: Path,
    shard_paths: Iterable[Path],
    source_id: str,
    repository: str = "https://github.com/ismartcoding/endict",
    source_sha256: str = "",
) -> dict[str, Any]:
    project_root = project_root.resolve()
    master_path = project_root / "vocabulary_master.csv"
    base_fields, rows = _read_master(master_path)
    target_keys = {row["lemma"].strip().casefold() for row in rows}
    if len(rows) != 6127 or len(target_keys) != 6127:
        raise ValueError(
            f"Expected 6,127 unique target rows before enrichment; got {len(rows)} rows and "
            f"{len(target_keys)} unique lemmas"
        )

    shard_paths = list(shard_paths)
    candidates, invalid_lines, matched_rows = collect_candidates(target_keys, shard_paths)
    subset_path = project_root / "data" / "cet4_metadata_subset.jsonl"
    subset_path.parent.mkdir(parents=True, exist_ok=True)
    with subset_path.open("w", encoding="utf-8", newline="\n") as handle:
        for candidate in sorted(
            matched_rows,
            key=lambda item: (
                str(item["word"]).casefold(), item["source_shard"], item["source_line"]
            ),
        ):
            handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")

    exact = ambiguous = unmatched = with_translation = with_pos = with_phonetic = 0
    with_source_pos = with_inferred_pos = 0
    for row in rows:
        key = row["lemma"].strip().casefold()
        items = candidates[key]
        records = [item["record"] for item in items]
        count = len(items)
        if count == 0:
            status = "unmatched"
            unmatched += 1
        elif count == 1:
            status = "exact"
            exact += 1
        else:
            status = "ambiguous_exact"
            ambiguous += 1

        translation = _join_unique(records, "translation")
        source_pos = _join_unique(records, "pos")
        inferred_pos = infer_pos_from_translation(translation) if not source_pos else ""
        resolved_pos = source_pos or inferred_pos
        phonetic = _join_unique(records, "phonetic")
        if translation:
            with_translation += 1
        if resolved_pos:
            with_pos += 1
        if source_pos:
            with_source_pos += 1
        if inferred_pos:
            with_inferred_pos += 1
        if phonetic:
            with_phonetic += 1

        row.update({
            "phonetic": phonetic,
            "english_definition": _join_unique(records, "definition"),
            "ecdict_translation": translation,
            "ecdict_pos": source_pos,
            "ecdict_exchange": _join_unique(records, "exchange"),
            "ecdict_examples": _join_unique(records, "examples"),
            "ecdict_collins": _join_unique(records, "collins"),
            "ecdict_oxford": _join_unique(records, "oxford"),
            "ecdict_tag": _join_unique(records, "tag"),
            "ecdict_bnc_frequency": _join_unique(records, "bnc"),
            "ecdict_contemporary_frequency": _join_unique(records, "frq"),
            "ecdict_detail": _join_unique(records, "detail"),
            "ecdict_audio": _join_unique(records, "audio"),
            "inferred_part_of_speech": inferred_pos,
            "pos_inference_method": "translation_prefix" if inferred_pos else "",
            "metadata_match_status": status,
            "metadata_candidate_count": count,
            "metadata_source": source_id if count else "",
        })
        if not row.get("part_of_speech") and resolved_pos:
            row["part_of_speech"] = resolved_pos
        if not row.get("chinese_meaning") and translation:
            row["chinese_meaning"] = translation
        row["status"] = {
            "exact": "metadata_exact_unreviewed",
            "ambiguous_exact": "metadata_ambiguous",
            "unmatched": "metadata_unmatched",
        }[status]
        row["needs_review"] = "yes"

    fields = base_fields + [field for field in EXTRA_FIELDS if field not in base_fields]
    _write_master(master_path, fields, rows)

    shard_info = [inspect_shard(path) for path in shard_paths]
    manifest = {
        "schema_version": 1,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "repository": repository,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "license": "MIT",
        "match_method": "case-insensitive exact whole-entry match",
        "target_count": len(rows),
        "exact_single_candidate": exact,
        "ambiguous_exact_candidates": ambiguous,
        "unmatched": unmatched,
        "matched_candidate_rows": len(matched_rows),
        "invalid_json_lines": invalid_lines,
        "with_translation": with_translation,
        "with_pos": with_pos,
        "with_source_pos": with_source_pos,
        "with_inferred_pos": with_inferred_pos,
        "with_phonetic": with_phonetic,
        "subset_file": subset_path.name,
        "subset_sha256": file_sha256(subset_path),
        "input_parts": [asdict(info) | {"path": Path(info.path).name} for info in shard_info],
    }
    manifest_path = project_root / "data" / "cet4_metadata_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def filter_ecdict_csv(master_path: Path, csv_path: Path, output_jsonl: Path) -> dict[str, int]:
    _, master_rows = _read_master(master_path)
    targets = {row["lemma"].strip().casefold() for row in master_rows}
    scanned = matched = 0
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source, output_jsonl.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        reader = csv.DictReader(source)
        for record in reader:
            scanned += 1
            word = str(record.get("word", "")).strip()
            if word.casefold() not in targets:
                continue
            record["_source_file"] = "ecdict.csv"
            record["_source_line"] = reader.line_num
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            matched += 1
    return {"scanned_rows": scanned, "matched_rows": matched}


def enrich_from_ecdict_csv(
    project_root: Path,
    csv_path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    csv_path = csv_path.resolve()
    actual_sha256 = file_sha256(csv_path)
    if expected_sha256 and actual_sha256 != expected_sha256.casefold():
        raise ValueError(
            f"ECDICT CSV SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    scratch_value = os.environ.get("KIROCREW_SCRATCH")
    if not scratch_value:
        raise RuntimeError("KIROCREW_SCRATCH is required for filtered intermediate data")
    filtered = Path(scratch_value) / "ecdict-cet4-exact.jsonl"
    scan = filter_ecdict_csv(project_root / "vocabulary_master.csv", csv_path, filtered)
    result = enrich_from_shards(
        project_root,
        [filtered],
        source_id=f"ECDICT/ecdict.csv@sha256:{actual_sha256}",
        repository="https://github.com/skywind3000/ECDICT",
        source_sha256=actual_sha256,
    )
    result.update(scan)
    (project_root / "data" / "cet4_metadata_manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_shard_enrichment(
    project_root: Path,
    scratch_root: Path | None = None,
    commit: str = DEFAULT_COMMIT,
    workers: int = 8,
    shard_count: int = 608,
) -> dict[str, Any]:
    if scratch_root is None:
        scratch_value = os.environ.get("KIROCREW_SCRATCH")
        if not scratch_value:
            raise RuntimeError("KIROCREW_SCRATCH is required for dictionary downloads")
        scratch_root = Path(scratch_value)
    shards = download_shards(
        scratch_root, commit=commit, workers=workers, shard_count=shard_count
    )
    return enrich_from_shards(
        project_root,
        shards,
        source_id=f"ismartcoding/endict@{commit}",
    )
