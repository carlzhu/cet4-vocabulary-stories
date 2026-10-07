"""The final PDFs must contain no .notdef box on any page.

Skipped when the PDFs have not been built (for example on a fresh checkout), so
the suite stays runnable; when they exist, this is a hard gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cet4_story.pdf_glyphs import scan_notdef

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOLUMES = (
    "CET4_Vocabulary_Stories.pdf",
    "CET4_Exercises.pdf",
    "CET4_Answer_Key.pdf",
    # Built by `build-sample-pdfs` from an older, near-duplicate renderer. It had
    # its own copies of all three box defects (157 + 11 boxes), which the first
    # round of fixes missed entirely because only the three root volumes were
    # checked. Listed here so a second renderer cannot silently regress.
    "build/CET4_Sample_Stories.pdf",
    "build/CET4_Sample_Exercises.pdf",
    "build/CET4_Sample_Answer_Key.pdf",
)


@pytest.mark.parametrize("name", VOLUMES)
def test_no_notdef_boxes_in_final_pdf(name: str) -> None:
    path = PROJECT_ROOT / name
    if not path.is_file():
        pytest.skip(f"{name} has not been built yet")

    result = scan_notdef(path)

    assert result["characters_drawn"] > 0, f"{name}: no text was traced at all"
    assert result["notdef_boxes"] == 0, (
        f"{name}: {result['notdef_boxes']} glyphs would print as boxes "
        f"({result['by_font']}); a paragraph styled with a Latin font is drawing "
        f"CJK, or a phonetics string is drawn with a font lacking IPA. "
        f"See cet4_story.pdf_builder.with_cjk_font."
    )
