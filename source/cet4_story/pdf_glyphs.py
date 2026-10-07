"""Definitive .notdef box detection for rendered PDFs.

A box means the renderer was asked for a glyph the font does not have and
substituted glyph id 0 (.notdef). PyMuPDF's text trace exposes the glyph id of
every character actually drawn, so ``gid == 0`` is proof of a box.

This is the check that catches the whole class, and it is the one to trust:

* counting U+FFFD in extracted text does not work - the PDF stores the correct
  character and only the glyph is missing, so extraction looks clean;
* comparing each text span's font cmap does not work either - the CID subsets have
  unreliable ToUnicode entries, so extraction returns ``\\x00`` or a guessed
  character (an attempt produced 203,870 false positives including ``的`` and
  ``—``);
* checking the source text against the font file catches only the cases you
  already thought of, and missed 548 boxes from Chinese drawn in a Latin style
  plus 744 more from Chinese quoted inside exercise prompts.

Prerequisite: PyMuPDF.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path


def scan_notdef(path: str | Path) -> dict[str, object]:
    """Return every .notdef box drawn in ``path``, with its page and font."""

    import fitz

    target = Path(path)
    document = fitz.open(str(target))
    by_char: Counter[str] = Counter()
    by_font: Counter[str] = Counter()
    samples: list[dict[str, object]] = []
    drawn = 0

    for page_number, page in enumerate(document, start=1):
        for span in page.get_texttrace():
            font = str(span.get("font", "?"))
            for entry in span.get("chars", []):
                drawn += 1
                glyph_id = entry[1] if len(entry) > 1 else None
                if glyph_id != 0:
                    continue
                codepoint = entry[0]
                character = (
                    chr(codepoint)
                    if isinstance(codepoint, int) and 0 < codepoint < 0x110000
                    else "?"
                )
                by_char[character] += 1
                by_font[font] += 1
                if len(samples) < 20:
                    samples.append(
                        {
                            "page": page_number,
                            "font": font,
                            "codepoint": (
                                f"U+{codepoint:04X}"
                                if isinstance(codepoint, int)
                                else "?"
                            ),
                        }
                    )
    document.close()

    return {
        "file": target.name,
        "characters_drawn": drawn,
        "notdef_boxes": sum(by_char.values()),
        "distinct_boxes": len(by_char),
        "by_character": {
            f"U+{ord(c):04X}": count for c, count in by_char.most_common()
        },
        "by_font": dict(by_font.most_common()),
        "samples": samples,
    }
