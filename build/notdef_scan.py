"""Report every .notdef box in the final PDFs, and fail if there is one.

Uses the package implementation so the CLI and the test suite share one detector.

Usage:
    python build/notdef_scan.py [file.pdf ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

from cet4_story.pdf_glyphs import scan_notdef  # noqa: E402

VOLUMES = (
    "CET4_Vocabulary_Stories.pdf",
    "CET4_Exercises.pdf",
    "CET4_Answer_Key.pdf",
)


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv[1:]] or [ROOT / name for name in VOLUMES]
    failed = False
    for path in targets:
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            return 1
        result = scan_notdef(path)
        ok = result["notdef_boxes"] == 0
        print(
            f"{path.name}: drawn={result['characters_drawn']} "
            f"notdef_boxes={result['notdef_boxes']} "
            f"distinct={result['distinct_boxes']} -> {'PASS' if ok else 'FAIL'}"
        )
        for label, count in list(result["by_character"].items())[:15]:
            print(f"    {label}: {count}")
        if result["by_font"]:
            print(f"    fonts: {result['by_font']}")
        for entry in list(result["samples"])[:5]:
            print(f"    e.g. page {entry['page']} {entry['font']} {entry['codepoint']}")
        if not ok:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
