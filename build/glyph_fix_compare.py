"""Render the same page region before and after the glyph fix, for inspection.

Text extraction cannot prove a box is gone - that is the whole reason this defect
slipped through. Pixels can: the same crop from the defective baseline and from
the rebuilt volume, stacked with labels.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import fitz  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def crop(path: Path, page_number: int, clip: fitz.Rect, scale: float) -> Image.Image:
    document = fitz.open(path)
    page = document.load_page(page_number - 1)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip)
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    document.close()
    return image


def main(argv: list[str]) -> int:
    before = ROOT / "build" / "qa" / "stories-baseline.pdf"
    after = ROOT / "CET4_Vocabulary_Stories.pdf"
    page_number = int(argv[1]) if len(argv) > 1 else 2

    # Left column of a vocabulary table: word, phonetic, POS.
    clip = fitz.Rect(35, 60, 210, 760)
    scale = 3.0
    top = crop(before, page_number, clip, scale)
    bottom = crop(after, page_number, clip, scale)

    label = 20
    width = max(top.width, bottom.width)
    sheet = Image.new(
        "RGB", (width + 8, top.height + bottom.height + label * 2 + 12), "white"
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 2), f"BEFORE fix - page {page_number} (boxes)", fill=(160, 0, 0))
    sheet.paste(top, (4, label))
    y = label + top.height + label
    draw.text((4, y - label + 2), f"AFTER fix - page {page_number}", fill=(0, 110, 0))
    sheet.paste(bottom, (4, y))
    destination = ROOT / "build" / "qa" / f"glyph-fix-page{page_number}.png"
    sheet.save(destination)
    print("written", destination, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
