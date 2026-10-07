"""Refresh one committed batch's hash after a cosmetic text correction.

`commit_batch` has no idempotence guard: re-committing an already-committed batch
would add its counts to the checkpoint a second time. When a committed batch needs
a text-only correction that leaves validation counts unchanged, re-validate it and
then update just that batch's hash.

Usage:
    python build/refresh_batch_hash.py batch-CH087-CH089
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.batch import (  # noqa: E402
    load_batch,
    load_checkpoint,
    save_checkpoint,
    verify_batch_integrity,
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    batch_id = argv[1]

    checkpoint = load_checkpoint(ROOT)
    if batch_id not in checkpoint.batch_hashes:
        print(f"{batch_id} is not in the checkpoint; nothing to refresh", file=sys.stderr)
        return 1

    batch = load_batch(ROOT / "drafts" / "batches" / f"{batch_id}.json")
    old = checkpoint.batch_hashes[batch_id]
    new = batch.sha256
    if old == new:
        print(f"{batch_id}: hash already current ({new[:16]}...)")
        return 0

    from dataclasses import replace

    updated = replace(
        checkpoint,
        batch_hashes={**checkpoint.batch_hashes, batch_id: new},
    )
    save_checkpoint(ROOT, updated)
    print(f"{batch_id}: hash {old[:16]}... -> {new[:16]}...")

    problems = verify_batch_integrity(ROOT, load_checkpoint(ROOT))
    print("integrity_problems:", problems)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
