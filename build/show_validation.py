"""Print a compact summary of a validate-batch JSON report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
document = json.loads(path.read_text(encoding="utf-8-sig"))
print(
    "valid=",
    document["schema_valid"]
    and document["plan_valid"]
    and document["coverage_valid"]
    and document["continuity_valid"],
    "| schema=", document["schema_valid"],
    "| plan=", document["plan_valid"],
    "| coverage=", document["coverage_valid"],
    "| continuity=", document["continuity_valid"],
)
print("counts:", json.dumps(document["validation_counts"], ensure_ascii=False))
print("chapters:")
for chapter in document["chapters"]:
    print(
        f"  {chapter['chapter_id']}: words={chapter['word_count']} "
        f"paras={chapter['paragraph_count']} new={chapter['verified_new']} "
        f"review={chapter['verified_review']}"
    )
errors = document.get("errors", [])
print(f"errors ({len(errors)}):")
for error in errors:
    print("  -", error)
