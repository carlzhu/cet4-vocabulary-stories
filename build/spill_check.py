"""Report pages whose extracted text is unusually short, to check for spill pages.

This measures the PDFs directly rather than reading ``reports/pdf_qa.json``: a
QA JSON can be left over from an earlier build, and reading it silently reports
the previous layout's numbers.

It also renders every short page into a contact sheet under ``build/qa/``, so the
sheet reviewers are pointed at is produced by this tool. It used to be made by hand,
which meant it silently described an older layout after every rebuild.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
sys.path.insert(0, str(ROOT / "build"))

from final_qa import VOLUMES, audit_pdf, contact_sheet  # noqa: E402

THRESHOLD = 400
QA_DIR = ROOT / "build" / "qa"


def main() -> int:
    sheets: list[Path] = []
    for name in VOLUMES:
        path = ROOT / name
        if not path.is_file():
            print(f"missing: {name}", file=sys.stderr)
            return 1
        result = audit_pdf(path)
        records = result["page_records"]
        lengths = sorted(record["characters"] for record in records)
        short = [record for record in records if record["characters"] < THRESHOLD]
        total = len(records)
        median = lengths[total // 2] if total else 0
        print(
            f"{name}: pages={total} median_chars={median} "
            f"min={lengths[0] if lengths else 0} pages_under_{THRESHOLD}={len(short)}"
        )
        for record in short[:12]:
            print(f"    page {record['page']}: {record['characters']} chars")
        if len(short) > 12:
            print(f"    ... {len(short) - 12} more")

        if short:
            destination = QA_DIR / f"contact-sparse-{path.stem}.png"
            contact_sheet(path, [r["page"] for r in short], destination, columns=3)
            sheets.append(destination)
            print(f"    contact sheet: {destination.relative_to(ROOT)}")

    print(f"contact sheets: {', '.join(str(s.relative_to(ROOT)) for s in sheets) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
