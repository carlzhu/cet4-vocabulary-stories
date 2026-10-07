"""Print the authoritative checkpoint state, never the on-disk diagnostic view.

`cet4-stories checkpoint-status` prints two blocks: the persisted `checkpoint`
(this is authoritative) and `rebuilt_from_disk` (a diagnostic that counts every
batch file present on disk, including batches that failed validation and were
therefore never committed). Reading the wrong one overstates progress, so this
helper reads the persisted checkpoint only.

Usage:
    .venv\\Scripts\\python.exe build\\checkpoint_state.py
"""

from __future__ import annotations

import json
import pathlib
import sys

CHECKPOINT = pathlib.Path("drafts/batches/checkpoint.json")


def main() -> int:
    if not CHECKPOINT.is_file():
        print(f"missing checkpoint: {CHECKPOINT}", file=sys.stderr)
        return 1
    data = json.loads(CHECKPOINT.read_text(encoding="utf-8-sig"))
    counts = data.get("validation_counts", {})
    print("authoritative checkpoint: drafts/batches/checkpoint.json")
    print(f"  complete_chapters : {counts.get('complete_chapters')}")
    print(f"  next_chapter_id   : {data.get('next_chapter_id')}")
    print(f"  batches           : {counts.get('batches')}")
    print(f"  needs_revision    : {counts.get('needs_revision')}")
    print(f"  verified_new      : {counts.get('verified_new')}")
    print(f"  verified_review   : {counts.get('verified_review')}")
    print(f"  batch_hashes      : {len(data.get('batch_hashes', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
