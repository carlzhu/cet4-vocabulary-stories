"""Regenerate the per-batch validation certificate for every committed batch.

Each certificate records whether a batch passed all four gates - schema, plan,
coverage and continuity - together with its counted totals. A reviewer can then
confirm that every batch was validated against the content actually shipped,
without running anything.

These files used to be produced by hand, by redirecting `validate-batch` output.
That made them orphans: nothing regenerated them, and after the content was revised
they still claimed to certify the older text. This tool exists so the certificates
track the batches, and `--check` fails if any has gone stale, which is what a
hand-maintained evidence file cannot do.

Usage:
    python build/refresh_validations.py           # rewrite every certificate
    python build/refresh_validations.py --check   # fail if any is missing or stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.batch import (  # noqa: E402
    continuity_path,
    load_batch,
    validate_batch,
)
from cet4_story.continuity import load_continuity  # noqa: E402
from cet4_story.project_data import load_project  # noqa: E402

BATCH_DIR = ROOT / "drafts" / "batches"
OUT_DIR = ROOT / "build"


def certificate_path(batch_id: str) -> Path:
    return OUT_DIR / f"val-{batch_id.removeprefix('batch-')}.json"


def build_certificate(project, states, path: Path) -> dict[str, object]:
    batch = load_batch(path)
    previous = [
        state for chapter_id, state in sorted(states.items())
        if chapter_id < batch.chapter_ids[0]
    ]
    outcome = validate_batch(
        batch.chapters,
        project,
        batch_id=batch.batch_id,
        previous_state=previous[-1] if previous else None,
        current_state=batch.continuity,
        require_continuity=True,
    )
    return outcome.to_dict()


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    project = load_project(ROOT)
    states = load_continuity(continuity_path(ROOT))
    batches = sorted(BATCH_DIR.glob("batch-*.json"))

    written = stale = invalid = 0
    for path in batches:
        payload = build_certificate(project, states, path)
        target = certificate_path(str(payload["batch_id"]))
        rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if target.is_file() and target.read_text(encoding="utf-8") == rendered:
            continue
        if check_only:
            stale += 1
            print(f"  STALE: {target.name}")
            continue
        target.write_text(rendered, encoding="utf-8")
        written += 1
        if not payload.get("valid", payload.get("schema_valid")):
            invalid += 1
            print(f"  INVALID: {payload['batch_id']}")

    print(f"batches          : {len(batches)}")
    print(f"certificates new : {written}")
    print(f"certificates stale: {stale}")
    print(f"batches invalid  : {invalid}")
    if check_only and stale:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
