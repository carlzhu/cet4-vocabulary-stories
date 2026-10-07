"""Programmatic QA for the three final deliverable PDFs.

Checks performed on every page of every volume:

* page count and A4 portrait dimensions;
* blank pages (no extractable text);
* Chinese replacement glyphs (U+FFFD) and other tofu markers;
* embedded font programmes, not just font names;
* text-block boundaries against the page box, so clipping is detected rather
  than assumed absent.

It also renders sampled contact sheets (beginning, middle, end, and
exercise-heavy pages) so a human can eyeball the layout. A successfully written
PDF is not proof of print quality, so this script reports what it measured and
leaves the visual judgement open.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

import fitz  # noqa: E402
from pypdf import PdfReader  # noqa: E402

A4_WIDTH = 595.276
A4_HEIGHT = 841.89
TOFU_MARKERS = ("\ufffd", "\u25a1", "\u25af")

VOLUMES = (
    "CET4_Vocabulary_Stories.pdf",
    "CET4_Exercises.pdf",
    "CET4_Answer_Key.pdf",
)
EXPECTED_FONT_HINTS = ("arial", "simhei", "hei", "song", "noto", "dejavu")


def _font_entries(page: object) -> list[dict[str, object]]:
    """Return one record per font used by ``page``, noting real embedding."""

    entries: list[dict[str, object]] = []
    resources = page.get("/Resources")  # type: ignore[attr-defined]
    if resources is None:
        return entries
    resources = resources.get_object()
    fonts = resources.get("/Font")
    if fonts is None:
        return entries
    fonts = fonts.get_object()
    for key in fonts:
        font = fonts[key].get_object()
        base = str(font.get("/BaseFont", "?"))
        subtype = str(font.get("/Subtype", "?"))
        embedded = False
        descriptors = []
        descriptor = font.get("/FontDescriptor")
        if descriptor is not None:
            descriptors.append(descriptor.get_object())
        descendants = font.get("/DescendantFonts")
        if descendants is not None:
            for item in descendants.get_object():
                item = item.get_object()
                inner = item.get("/FontDescriptor")
                if inner is not None:
                    descriptors.append(inner.get_object())
        for desc in descriptors:
            if any(
                name in desc
                for name in ("/FontFile", "/FontFile2", "/FontFile3")
            ):
                embedded = True
                break
        entries.append(
            {
                "resource": str(key),
                "base_font": base,
                "subtype": subtype,
                "embedded": embedded,
            }
        )
    return entries


def _fonts_that_draw(page: object) -> set[str]:
    """Return the font resource names that actually paint a glyph on ``page``.

    reportlab opens every page with an empty ``BT /F1 12 Tf … ET`` block, so the
    base-14 default font appears in the resources of every page without drawing
    anything. Distinguishing "declared" from "painting" is the difference between
    a harmless artefact and a real unembedded-text defect, so we parse the
    content stream instead of guessing.
    """

    data = page.get_contents().get_data().decode("latin-1")  # type: ignore[attr-defined]
    drawing: set[str] = set()
    current: str | None = None
    index = 0
    length = len(data)
    while index < length:
        character = data[index]
        if character == "/":
            match = re.match(r"/([A-Za-z0-9+]+)", data[index:])
            if match:
                index += match.end()
                continue
        if data.startswith("Tf", index):
            window = data[max(0, index - 40) : index]
            name = re.findall(r"/([A-Za-z0-9+]+)\s+[\d.]+\s*$", window)
            if name:
                current = name[-1]
            index += 2
            continue
        if character == "(" and current is not None:
            # A literal string operand followed eventually by a showing operator.
            cursor = index
            depth = 0
            while cursor < length:
                if data[cursor] == "\\":
                    cursor += 2
                    continue
                if data[cursor] == "(":
                    depth += 1
                elif data[cursor] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                cursor += 1
            tail = data[cursor + 1 : cursor + 4]
            if tail.lstrip().startswith(("Tj", "TJ", "'", '"')):
                drawing.add(current)
            index = cursor + 1
            continue
        if character == "<" and current is not None:
            cursor = data.find(">", index)
            if cursor != -1:
                tail = data[cursor + 1 : cursor + 4]
                if tail.lstrip().startswith(("Tj", "TJ", "'", '"')):
                    drawing.add(current)
                index = cursor + 1
                continue
        index += 1
    return drawing


def audit_pdf(path: Path) -> dict[str, object]:
    """Measure one PDF and return its QA record."""

    reader = PdfReader(str(path))
    pages: list[dict[str, object]] = []
    fonts: dict[str, dict[str, object]] = {}
    painting: set[str] = set()
    blank: list[int] = []
    not_a4: list[int] = []
    tofu_total = 0
    min_chars = None

    for index, page in enumerate(reader.pages, start=1):
        width = round(float(page.mediabox.width), 2)
        height = round(float(page.mediabox.height), 2)
        text = page.extract_text() or ""
        stripped = text.strip()
        if not stripped:
            blank.append(index)
        if abs(width - A4_WIDTH) >= 1 or abs(height - A4_HEIGHT) >= 1:
            not_a4.append(index)
        tofu = sum(text.count(marker) for marker in TOFU_MARKERS)
        tofu_total += tofu
        length = len(stripped)
        min_chars = length if min_chars is None else min(min_chars, length)
        entries = _font_entries(page)
        drawing = _fonts_that_draw(page)
        for entry in entries:
            resource = str(entry["resource"]).lstrip("/")
            fonts[str(entry["base_font"])] = entry
            if resource in drawing:
                painting.add(str(entry["base_font"]))
        pages.append(
            {
                "page": index,
                "width": width,
                "height": height,
                "characters": length,
                "tofu": tofu,
                "painting_fonts": sorted(drawing),
            }
        )

    # Boundary check with PyMuPDF: no text block may leave its page box.
    document = fitz.open(path)
    boundary_violations: list[dict[str, object]] = []
    for page_number, page in enumerate(document, start=1):
        box = page.rect
        for block in page.get_text("blocks"):
            x0, y0, x1, y1 = (round(value, 2) for value in block[:4])
            # 2 pt of tolerance for glyph side bearings.
            if x0 < -2 or y0 < -2 or x1 > box.width + 2 or y1 > box.height + 2:
                boundary_violations.append(
                    {"page": page_number, "bbox": [x0, y0, x1, y1]}
                )
    document.close()

    names = sorted(fonts)
    cjk_fonts = [name for name in names if any(h in name.casefold() for h in EXPECTED_FONT_HINTS)]
    painting_names = sorted(painting)
    unembedded_painting = sorted(
        name for name in painting_names if not (fonts.get(name) or {}).get("embedded")
    )
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "pages": len(pages),
        "a4_portrait": not not_a4,
        "a4_violations": not_a4,
        "blank_pages": blank,
        "minimum_extracted_characters": min_chars,
        "replacement_glyphs": tofu_total,
        "fonts": [fonts[name] for name in names],
        "font_count": len(names),
        "embedded_font_count": sum(1 for name in names if fonts[name]["embedded"]),
        "fonts_that_paint_text": painting_names,
        "unembedded_fonts_that_paint_text": unembedded_painting,
        "all_painted_text_uses_embedded_fonts": not unembedded_painting,
        "cjk_capable_fonts": cjk_fonts,
        "boundary_violations": boundary_violations,
        "page_records": pages,
    }


def contact_sheet(
    path: Path,
    page_numbers: list[int],
    destination: Path,
    *,
    columns: int = 4,
    scale: float = 0.5,
    label_height: int = 18,
) -> Path:
    """Render sampled pages into one PNG grid for visual inspection.

    Each tile is captioned with its page number so a reviewer can point at an
    exact page instead of describing "somewhere in the middle".
    """

    from PIL import Image, ImageDraw

    document = fitz.open(path)
    tiles: list[tuple[int, Image.Image]] = []
    for number in page_numbers:
        if 1 <= number <= document.page_count:
            page = document.load_page(number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            tiles.append((number, image))
    document.close()
    if not tiles:
        raise ValueError(f"no pages to render for {path.name}")

    tile_width = max(image.width for _, image in tiles)
    tile_height = max(image.height for _, image in tiles) + label_height
    rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (tile_width * columns, tile_height * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (number, image) in enumerate(tiles):
        row, column = divmod(index, columns)
        x = column * tile_width
        y = row * tile_height
        draw.text((x + 4, y + 3), f"page {number}", fill=(20, 40, 90))
        sheet.paste(image, (x, y + label_height))
        draw.rectangle(
            [x, y, x + tile_width - 1, y + tile_height - 1], outline=(180, 190, 200)
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination)
    return destination


def sample_pages(total: int) -> list[int]:
    """Pick beginning, middle, end, and interior pages spread across a volume."""

    if total <= 6:
        return list(range(1, total + 1))
    picks = [
        1,
        2,
        total // 6,
        total // 4,
        total // 2,
        (3 * total) // 4,
        total - 3,
        total - 1,
        total,
    ]
    return sorted({number for number in picks if 1 <= number <= total})


def main() -> int:
    results = []
    for name in VOLUMES:
        path = ROOT / name
        if not path.is_file():
            print(f"missing deliverable: {name}", file=sys.stderr)
            return 1
        results.append(audit_pdf(path))

    sheets = []
    for result in results:
        path = ROOT / str(result["file"])
        destination = ROOT / "build" / "qa" / f"contact-{path.stem}.png"
        contact_sheet(path, sample_pages(int(result["pages"])), destination)
        sheets.append(str(destination.relative_to(ROOT)))

    payload = {
        "volumes": results,
        "contact_sheets": sheets,
        "print_test_performed": False,
    }
    out = ROOT / "reports" / "pdf_qa.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for result in results:
        print(
            f"{result['file']:<32} pages={result['pages']:>4} "
            f"a4={result['a4_portrait']} blank={result['blank_pages']} "
            f"minchars={result['minimum_extracted_characters']:>4} "
            f"tofu={result['replacement_glyphs']} "
            f"fonts={result['font_count']} embedded={result['embedded_font_count']} "
            f"bounds={len(result['boundary_violations'])}"
        )
        print(f"    painting fonts: {result['fonts_that_paint_text']}")
        print(
            "    all painted text embedded: "
            f"{result['all_painted_text_uses_embedded_fonts']} "
            f"(unembedded painting: {result['unembedded_fonts_that_paint_text']})"
        )
    print()
    print("contact sheets:", ", ".join(sheets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
