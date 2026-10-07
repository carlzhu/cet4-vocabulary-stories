from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path
from typing import Any

from cet4_story.pdf_text import with_cjk_font

A4_WIDTH = 595.275590551
A4_HEIGHT = 841.88976378
DARK_BLUE = "#173B57"
MID_BLUE = "#2E617C"
TEAL = "#176B6B"
LIGHT_BLUE = "#DDEBF2"
PALE_BLUE = "#EDF5F8"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _term_pattern(terms: list[str]) -> re.Pattern[str]:
    alternatives = sorted((re.escape(term) for term in terms), key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z])(?:" + "|".join(alternatives) + r")(?![A-Za-z])", re.I)


def _marked_text(text: str, new_terms: list[str], review_terms: list[str]) -> str:
    new_keys = {term.casefold() for term in new_terms}
    review_keys = {term.casefold() for term in review_terms}
    pattern = _term_pattern(new_terms + review_terms)
    pieces: list[str] = []
    end = 0
    for match in pattern.finditer(text):
        pieces.append(html.escape(text[end:match.start()]))
        value = html.escape(match.group(0))
        key = match.group(0).casefold()
        if key in new_keys:
            pieces.append(f'<b><font color="{DARK_BLUE}">{value}</font></b>')
        elif key in review_keys:
            pieces.append(f'<i><u><font color="{TEAL}">{value}</font></u></i>')
        else:
            pieces.append(value)
        end = match.end()
    pieces.append(html.escape(text[end:]))
    return "".join(pieces)


def _first_value(value: str, limit: int) -> str:
    first = value.split(" || ", 1)[0].replace("\\n", "；").replace("\n", "；").strip()
    if len(first) <= limit:
        return first
    return first[: limit - 1].rstrip() + "…"


def verify_samples(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    samples = json.loads((project_root / "drafts" / "sample_chapters.json").read_text(encoding="utf-8"))
    master = {row["vocabulary_id"]: row for row in _read_csv(project_root / "vocabulary_master.csv")}
    plan = {row["article_id"]: row for row in _read_csv(project_root / "curriculum_plan.csv")}
    coverage_rows: list[dict[str, Any]] = []
    chapter_results: list[dict[str, Any]] = []

    for chapter in samples["chapters"]:
        article_id = chapter["article_id"]
        planned = plan[article_id]
        text = " ".join(chapter["english_paragraphs"])
        sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        new_ids = [value for value in planned["new_vocabulary_ids"].split("|") if value]
        review_ids = [value for value in planned["review_vocabulary_ids"].split("|") if value]
        missing: list[str] = []
        for role, vocabulary_ids in (("new", new_ids), ("review", review_ids)):
            for vocabulary_id in vocabulary_ids:
                lemma = master[vocabulary_id]["lemma"]
                pattern = re.compile(
                    r"(?<![A-Za-z])" + re.escape(lemma) + r"(?![A-Za-z])", re.I
                )
                matches = list(pattern.finditer(text))
                if not matches:
                    missing.append(lemma)
                    continue
                context = next(
                    (sentence for sentence in sentence_parts if pattern.search(sentence)), text
                )
                coverage_rows.append({
                    "vocabulary_id": vocabulary_id,
                    "lemma": lemma,
                    "article_id": article_id,
                    "learning_role": role,
                    "occurrence_count": len(matches),
                    "original_form": lemma,
                    "matched_form": matches[0].group(0),
                    "context_sentence": context,
                    "coverage_status": "draft_sample_verified",
                    "match_method": "case-insensitive exact whole-entry regex",
                    "review_note": "Requires semantic/human review before final coverage credit",
                })
        exercise_ids = {item["id"] for item in chapter["exercises"]}
        answer_ids = {item["id"] for item in chapter["answers"]}
        if exercise_ids != answer_ids:
            raise ValueError(f"Exercise/answer mismatch in {article_id}")
        if missing:
            raise ValueError(f"Missing planned terms in {article_id}: {missing}")
        chapter_results.append({
            "article_id": article_id,
            "english_words": len(text.split()),
            "new_terms": len(new_ids),
            "review_terms": len(review_ids),
            "exercises": len(exercise_ids),
        })

    output = project_root / "build" / "sample_coverage.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "vocabulary_id", "lemma", "article_id", "learning_role", "occurrence_count",
        "original_form", "matched_form", "context_sentence", "coverage_status",
        "match_method", "review_note",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(coverage_rows)
    return {
        "chapters": chapter_results,
        "coverage_rows": len(coverage_rows),
        "new_terms_verified": sum(item["new_terms"] for item in chapter_results),
        "review_terms_verified": sum(item["review_terms"] for item in chapter_results),
    }


def _register_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fonts = {
        "CETEnglish": Path(r"C:\WINDOWS\Fonts\arial.ttf"),
        "CETEnglishBold": Path(r"C:\WINDOWS\Fonts\arialbd.ttf"),
        "CETChinese": Path(r"C:\WINDOWS\Fonts\simhei.ttf"),
    }
    for name, path in fonts.items():
        if not path.exists():
            raise FileNotFoundError(f"Required font not found: {path}")
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "CETEnglish", normal="CETEnglish", bold="CETEnglishBold"
    )


def _styles() -> dict[str, Any]:
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm

    return {
        "chapter": ParagraphStyle(
            "Chapter", fontName="CETEnglishBold", fontSize=15, leading=18,
            textColor=DARK_BLUE, spaceAfter=2 * mm, alignment=TA_LEFT,
        ),
        "chinese_title": ParagraphStyle(
            "ChineseTitle", fontName="CETChinese", fontSize=11, leading=15,
            textColor=MID_BLUE, spaceAfter=3 * mm,
        ),
        "section": ParagraphStyle(
            "Section", fontName="CETEnglishBold", fontSize=10.5, leading=13,
            textColor=DARK_BLUE, spaceBefore=2 * mm, spaceAfter=1.5 * mm,
        ),
        "english": ParagraphStyle(
            "English", fontName="CETEnglish", fontSize=9.4, leading=13.1,
            textColor=DARK_BLUE, spaceAfter=2.2 * mm, allowWidows=0, allowOrphans=0,
        ),
        "chinese": ParagraphStyle(
            "Chinese", fontName="CETChinese", fontSize=8.8, leading=13,
            textColor=DARK_BLUE, spaceAfter=2.2 * mm, allowWidows=0, allowOrphans=0,
        ),
        "meta": ParagraphStyle(
            "Meta", fontName="CETChinese", fontSize=7.8, leading=10,
            textColor=MID_BLUE, spaceAfter=2 * mm,
        ),
        "table_header": ParagraphStyle(
            "TableHeader", fontName="CETChinese", fontSize=7.3, leading=8.5,
            textColor=DARK_BLUE, alignment=TA_CENTER,
        ),
        "table": ParagraphStyle(
            "Table", fontName="CETChinese", fontSize=6.7, leading=8.0,
            textColor=DARK_BLUE,
        ),
        "question": ParagraphStyle(
            "Question", fontName="CETEnglish", fontSize=9.2, leading=12.5,
            textColor=DARK_BLUE, spaceAfter=1.3 * mm,
        ),
        "answer": ParagraphStyle(
            "Answer", fontName="CETChinese", fontSize=8.5, leading=12,
            textColor=DARK_BLUE, spaceAfter=1.5 * mm,
        ),
    }


def _footer(canvas: Any, document: Any) -> None:
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm

    canvas.saveState()
    canvas.setFillColor(HexColor(MID_BLUE))
    canvas.setFont("CETEnglish", 7.5)
    canvas.drawString(15 * mm, 9 * mm, "CET-4 VOCABULARY STORY — COLOR-CARTRIDGE EDITION")
    canvas.drawRightString(A4_WIDTH - 15 * mm, 9 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_sample_pdfs(project_root: Path) -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate,
        Spacer, TableStyle,
    )

    project_root = project_root.resolve()
    _register_fonts()
    styles = _styles()
    samples = json.loads((project_root / "drafts" / "sample_chapters.json").read_text(encoding="utf-8"))
    master = {row["vocabulary_id"]: row for row in _read_csv(project_root / "vocabulary_master.csv")}
    plan = {row["article_id"]: row for row in _read_csv(project_root / "curriculum_plan.csv")}
    build = project_root / "build"
    build.mkdir(parents=True, exist_ok=True)

    story_path = build / "CET4_Sample_Stories.pdf"
    story_doc = SimpleDocTemplate(
        str(story_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title="CET-4 Vocabulary Story Samples",
        author="CET-4 Vocabulary Stories Project",
    )
    story: list[Any] = []
    sample_labels = {
        "CH001": "Long-body stress sample",
        "CH050": "Translation and vocabulary-table stress sample",
        "CH090": "Dense exercise-source stress sample",
    }
    cumulative = 0
    for chapter_index, chapter in enumerate(samples["chapters"]):
        if chapter_index:
            story.append(PageBreak())
        planned = plan[chapter["article_id"]]
        new_ids = [value for value in planned["new_vocabulary_ids"].split("|") if value]
        review_ids = [value for value in planned["review_vocabulary_ids"].split("|") if value]
        new_terms = [master[value]["lemma"] for value in new_ids]
        review_terms = [master[value]["lemma"] for value in review_ids]
        cumulative += len(new_terms)
        story.extend([
            Paragraph(
                f"CET-4 VOCABULARY STORY · Chapter {int(planned['chapter_number']):03d}/137",
                styles["meta"],
            ),
            Paragraph(html.escape(chapter["english_title"]), styles["chapter"]),
            Paragraph(html.escape(chapter["chinese_title"]), styles["chinese_title"]),
            Paragraph(
                html.escape(
                    f"{sample_labels[chapter['article_id']]} · Theme: {chapter['theme']} · "
                    f"New: {len(new_terms)} · Review: {len(review_terms)} · "
                    f"Planned cumulative progress: {cumulative}/6,127"
                ),
                styles["meta"],
            ),
            Paragraph("English Story", styles["section"]),
        ])
        for paragraph in chapter["english_paragraphs"]:
            story.append(Paragraph(_marked_text(paragraph, new_terms, review_terms), styles["english"]))
        story.append(Paragraph(with_cjk_font("中文翻译"), styles["section"]))
        for paragraph in chapter["chinese_paragraphs"]:
            story.append(Paragraph(html.escape(paragraph), styles["chinese"]))
        story.extend([PageBreak(), Paragraph(
            'Core Vocabulary · <font name="CETChinese">核心词汇</font>', styles["section"]
        )])
        table_data: list[list[Any]] = [[
            Paragraph("Word / Pronunciation", styles["table_header"]),
            Paragraph("Context meaning / source example", styles["table_header"]),
        ]]
        for vocabulary_id in new_ids:
            row = master[vocabulary_id]
            # Draw the lemma and the IPA with Arial. The cell style is CETChinese
            # (SimHei), which cannot draw 15 of the 19 non-ASCII phonetics
            # characters, so those rows printed as .notdef boxes. Mirrors
            # pdf_builder._vocabulary_table.
            left = (
                f'<font name="CETEnglish"><b>{html.escape(row["lemma"])}</b><br/>'
                f'{html.escape(row["phonetic"] or "phonetic unavailable")}</font><br/>'
                f'POS: {html.escape(row["part_of_speech"] or "review required")}'
            )
            meaning = _first_value(row["chinese_meaning"], 70)
            example = _first_value(row["ecdict_examples"], 110)
            right = (
                f"{html.escape(meaning)}<br/>"
                f"Collocation: — (not independently sourced)<br/>"
                f"Example: {html.escape(example or 'No reliable source example available.')}"
            )
            table_data.append([
                Paragraph(left, styles["table"]),
                Paragraph(right, styles["table"]),
            ])
        vocabulary_table = LongTable(
            table_data, colWidths=[48 * mm, 127 * mm], repeatRows=1,
            splitByRow=1, hAlign="LEFT",
        )
        vocabulary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor(LIGHT_BLUE)),
            ("TEXTCOLOR", (0, 0), (-1, -1), HexColor(DARK_BLUE)),
            ("GRID", (0, 0), (-1, -1), 0.35, HexColor(MID_BLUE)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.8 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.8 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 0.7 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0.7 * mm),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor(PALE_BLUE)]),
        ]))
        story.append(vocabulary_table)
    story_doc.build(story, onFirstPage=_footer, onLaterPages=_footer)

    exercise_path = build / "CET4_Sample_Exercises.pdf"
    exercise_doc = SimpleDocTemplate(
        str(exercise_path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title="CET-4 Sample Exercises",
    )
    exercise_story: list[Any] = []
    for index, chapter in enumerate(samples["chapters"]):
        if index:
            exercise_story.append(PageBreak())
        exercise_story.extend([
            Paragraph(f"{chapter['article_id']} · {html.escape(chapter['english_title'])}", styles["chapter"]),
            Paragraph("Memory Practice · 独立作答", styles["chinese_title"]),
        ])
        for number, question in enumerate(chapter["exercises"], start=1):
            options = "<br/>".join(
                f"{chr(64 + option_index)}. {html.escape(option)}"
                for option_index, option in enumerate(question["options"], start=1)
            )
            exercise_story.append(KeepTogether([
                Paragraph(
                    with_cjk_font(
                        f"<b>{number}.</b> {html.escape(question['prompt'])}"
                    ),
                    styles["question"],
                ),
                Paragraph(with_cjk_font(options), styles["question"]),
                Spacer(1, 3 * mm),
            ]))
        exercise_story.append(Paragraph("Score: ____ / 5", styles["question"]))
    exercise_doc.build(exercise_story, onFirstPage=_footer, onLaterPages=_footer)

    answer_path = build / "CET4_Sample_Answer_Key.pdf"
    answer_doc = SimpleDocTemplate(
        str(answer_path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title="CET-4 Sample Answer Key",
    )
    answer_story: list[Any] = [Paragraph(
        'CET-4 Sample Answer Key · <font name="CETChinese">样稿答案</font>',
        styles["chapter"],
    )]
    for chapter in samples["chapters"]:
        answer_story.append(Paragraph(
            f"{chapter['article_id']} · {html.escape(chapter['english_title'])}", styles["section"]
        ))
        for number, answer in enumerate(chapter["answers"], start=1):
            answer_story.append(Paragraph(
                f"<b>{number}. {html.escape(answer['answer'])}</b> — "
                f"{html.escape(answer['explanation'])}", styles["answer"]
            ))
    answer_doc.build(answer_story, onFirstPage=_footer, onLaterPages=_footer)

    return {
        "story_pdf": str(story_path),
        "exercise_pdf": str(exercise_path),
        "answer_pdf": str(answer_path),
    }


def inspect_pdf(path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    sizes: list[tuple[float, float]] = []
    text_lengths: list[int] = []
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        sizes.append((width, height))
        text_lengths.append(len((page.extract_text() or "").strip()))
    a4_ok = all(
        abs(width - A4_WIDTH) < 1 and abs(height - A4_HEIGHT) < 1
        for width, height in sizes
    )
    return {
        "path": str(path),
        "pages": len(reader.pages),
        "a4_portrait": a4_ok,
        "blank_pages": [index + 1 for index, length in enumerate(text_lengths) if length == 0],
        "minimum_extracted_characters": min(text_lengths, default=0),
    }


def inspect_sample_pdfs(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    build = project_root / "build"
    names = [
        "CET4_Sample_Stories.pdf",
        "CET4_Sample_Exercises.pdf",
        "CET4_Sample_Answer_Key.pdf",
    ]
    reports = [inspect_pdf(build / name) for name in names]
    if not all(report["a4_portrait"] for report in reports):
        raise ValueError("At least one sample PDF is not A4 portrait")
    if any(report["blank_pages"] for report in reports):
        raise ValueError("At least one sample PDF contains a blank page")
    return {"pdfs": reports}
