"""Printable A4 rendering for any validated set of curriculum chapters.

The validated sample builder hard-codes three chapters; this module keeps its
typography, colour policy, and vocabulary marking rules and renders arbitrary
chapter sets: per-chapter handouts and combined volumes for the three required
deliverables (story/vocabulary, exercises, answer key).
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from cet4_story.batch import load_batches
from cet4_story.models import Chapter
from cet4_story.project_data import ProjectData, load_project
from cet4_story.pdf_text import with_cjk_font as _with_cjk_font
from cet4_story.sample_builder import (
    DARK_BLUE,
    LIGHT_BLUE,
    MID_BLUE,
    PALE_BLUE,
    _first_value,
    _footer,
    _marked_text,
    _register_fonts,
    _styles,
)

SAMPLE_CHAPTERS_PATH = Path("drafts") / "sample_chapters.json"
DEFAULT_PREVIEW_DIR = Path("build") / "preview"
TOTAL_TARGETS = 6127
CHAPTER_TOTAL = 137


class PdfBuildError(ValueError):
    """A chapter set could not be rendered."""


def load_chapters(root: str | Path) -> dict[str, Chapter]:
    """Load every chapter available on disk: approved samples plus all batches."""

    project_root = Path(root).resolve()
    chapters: dict[str, Chapter] = {}
    sample_path = project_root / SAMPLE_CHAPTERS_PATH
    if sample_path.is_file():
        import json

        document = json.loads(sample_path.read_text(encoding="utf-8"))
        for entry in document["chapters"]:
            chapter = Chapter.from_dict(entry)
            chapters[chapter.article_id] = chapter
    for batch in load_batches(project_root).values():
        for chapter in batch.chapters:
            if chapter.article_id in chapters:
                raise PdfBuildError(f"chapter {chapter.article_id} appears twice on disk")
            chapters[chapter.article_id] = chapter
    return chapters


def select_chapters(
    root: str | Path, selector: str = "completed"
) -> list[Chapter]:
    """Return chapters in order for ``completed``, ``all``, or an id range."""

    chapters = load_chapters(root)
    text = (selector or "completed").strip().upper()
    if text in {"COMPLETED", "ALL", ""}:
        return [chapters[key] for key in sorted(chapters)]
    if "-" in text:
        start, _, end = text.partition("-")
        start = start if start.startswith("CH") else f"CH{start}"
        end = end if end.startswith("CH") else f"CH{end}"
        wanted = [
            f"CH{number:03d}"
            for number in range(int(start[2:]), int(end[2:]) + 1)
        ]
    else:
        wanted = [text if text.startswith("CH") else f"CH{text}"]
    missing = [chapter_id for chapter_id in wanted if chapter_id not in chapters]
    if missing:
        raise PdfBuildError("chapters not on disk yet: " + ", ".join(missing))
    return [chapters[chapter_id] for chapter_id in wanted]


def _plan(project: ProjectData, article_id: str) -> Mapping[str, str]:
    return project.source.chapter_record(article_id)


def _ids(value: str) -> list[str]:
    return [part for part in (value or "").split("|") if part]


def _term_data(
    project: ProjectData, article_id: str
) -> tuple[list[str], list[str], list[str], list[str]]:
    planned = _plan(project, article_id)
    new_ids = _ids(planned.get("new_vocabulary_ids", ""))
    review_ids = _ids(planned.get("review_vocabulary_ids", ""))
    new_terms = [project.vocabulary_by_id[value]["lemma"] for value in new_ids]
    review_terms = [project.vocabulary_by_id[value]["lemma"] for value in review_ids]
    return new_ids, review_ids, new_terms, review_terms


_CJK_RUN = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]+")


def with_cjk_font(text: str) -> str:
    """Wrap CJK runs so a Latin-styled paragraph can actually draw them.

    Kept as a re-export so ``cet4_story.pdf_builder.with_cjk_font`` keeps working;
    the implementation is shared with ``sample_builder`` via ``pdf_text`` to keep
    the module graph acyclic.
    """

    return _with_cjk_font(text)


def _vocabulary_table(project: ProjectData, new_ids: Sequence[str]) -> Any:
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, TableStyle

    styles = _styles()
    data: list[list[Any]] = [[
        Paragraph("Word / Pronunciation", styles["table_header"]),
        Paragraph("Context meaning / source example", styles["table_header"]),
    ]]
    for vocabulary_id in new_ids:
        row = project.vocabulary_by_id[vocabulary_id]
        # Latin and IPA text must use the Latin font: SimHei has no glyph for 15
        # of the 19 non-ASCII phonetics characters (æ ð ŋ ɒ ɔ ə ɜ ɪ ʃ ʌ ʒ ˈ ˌ є ә),
        # which rendered as .notdef boxes in 4,540 of 6,127 rows. Arial covers all
        # of them, so both the lemma and the transcription are tagged with it.
        phonetic = html.escape(row.get("phonetic") or "phonetic unavailable")
        left = (
            f'<font name="CETEnglish"><b>{html.escape(row["lemma"])}</b></font><br/>'
            f'<font name="CETEnglish">{phonetic}</font><br/>'
            f"POS: {html.escape(row.get('part_of_speech') or row.get('ecdict_pos') or 'review required')}"
        )
        meaning = _first_value(row.get("chinese_meaning", ""), 70)
        example = _first_value(
            row.get("ecdict_examples", "") or row.get("definition", ""), 110
        )
        right = (
            f"{html.escape(meaning)}<br/>"
            f"Collocation: — (not independently sourced)<br/>"
            f"Example: {html.escape(example or 'No reliable source example available.')}"
        )
        data.append([Paragraph(left, styles["table"]), Paragraph(right, styles["table"])])
    table = LongTable(
        data, colWidths=[48 * mm, 127 * mm], repeatRows=1, splitByRow=1, hAlign="LEFT"
    )
    table.setStyle(TableStyle([
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
    return table


def build_story_pdf(
    path: str | Path,
    project: ProjectData,
    chapters: Sequence[Chapter],
    *,
    title: str,
    subtitle: str = "",
) -> Path:
    """Render story, translation, and the core-vocabulary table."""

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    _register_fonts()
    styles = _styles()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(target), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm, title=title,
        author="CET-4 Vocabulary Stories Project",
    )
    flow: list[Any] = []
    if subtitle:
        flow.append(Paragraph(html.escape(subtitle), styles["meta"]))
    cumulative = 0
    for index, chapter in enumerate(chapters):
        if index:
            flow.append(PageBreak())
        new_ids, _, new_terms, review_terms = _term_data(project, chapter.article_id)
        planned = _plan(project, chapter.article_id)
        cumulative += len(new_terms)
        flow.extend([
            Paragraph(
                f"CET-4 VOCABULARY STORY · Chapter "
                f"{int(planned.get('chapter_number', 0)):03d}/{CHAPTER_TOTAL}",
                styles["meta"],
            ),
            Paragraph(html.escape(chapter.english_title), styles["chapter"]),
            Paragraph(html.escape(chapter.chinese_title), styles["chinese_title"]),
            Paragraph(
                html.escape(
                    f"Theme: {chapter.theme} · New: {len(new_terms)} · "
                    f"Review: {len(review_terms)} · "
                    f"Planned cumulative progress: {cumulative}/{TOTAL_TARGETS:,}"
                ),
                styles["meta"],
            ),
            Paragraph("English Story", styles["section"]),
        ])
        for paragraph in chapter.english_paragraphs:
            flow.append(
                Paragraph(
                    _marked_text(paragraph, new_terms, review_terms), styles["english"]
                )
            )
        flow.append(Paragraph(with_cjk_font("中文翻译"), styles["section"]))
        for paragraph in chapter.chinese_paragraphs:
            flow.append(Paragraph(html.escape(paragraph), styles["chinese"]))
        flow.append(PageBreak())
        flow.append(
            Paragraph(
                'Core Vocabulary · <font name="CETChinese">核心词汇</font>',
                styles["section"],
            )
        )
        flow.append(_vocabulary_table(project, new_ids))
    document.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return target


def build_exercise_pdf(
    path: str | Path,
    chapters: Sequence[Chapter],
    *,
    title: str,
) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    )

    _register_fonts()
    styles = _styles()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(target), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title=title,
    )
    flow: list[Any] = []
    for index, chapter in enumerate(chapters):
        if index:
            flow.append(PageBreak())
        flow.extend([
            Paragraph(
                f"{chapter.article_id} · {html.escape(chapter.english_title)}",
                styles["chapter"],
            ),
            Paragraph("Memory Practice · 独立作答", styles["chinese_title"]),
        ])
        for number, question in enumerate(chapter.exercises, start=1):
            options = "<br/>".join(
                f"{chr(64 + option_index)}. {html.escape(option)}"
                for option_index, option in enumerate(question.options, start=1)
            )
            flow.append(KeepTogether([
                Paragraph(
                    with_cjk_font(f"<b>{number}.</b> {html.escape(question.prompt)}"),
                    styles["question"],
                ),
                Paragraph(with_cjk_font(options), styles["question"]),
                Spacer(1, 3 * mm),
            ]))
        flow.append(Paragraph("Score: ____ / 5", styles["question"]))
    document.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return target


def build_answer_pdf(
    path: str | Path,
    chapters: Sequence[Chapter],
    *,
    title: str,
) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    _register_fonts()
    styles = _styles()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(target), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title=title,
    )
    flow: list[Any] = [Paragraph(
        html.escape(title) + ' · <font name="CETChinese">答案与解析</font>',
        styles["chapter"],
    )]
    for chapter in chapters:
        flow.append(Paragraph(
            f"{chapter.article_id} · {html.escape(chapter.english_title)}", styles["section"]
        ))
        for number, answer in enumerate(chapter.answers, start=1):
            flow.append(Paragraph(
                f"<b>{number}. {html.escape(answer.answer)}</b> — "
                f"{html.escape(answer.explanation)}",
                styles["answer"],
            ))
    document.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return target


def build_volume_pdfs(
    root: str | Path,
    chapters: Sequence[Chapter],
    out_dir: str | Path,
    *,
    prefix: str = "CET4_Preview",
) -> dict[str, str]:
    """Render the combined story, exercise, and answer volumes."""

    project = load_project(root)
    directory = Path(out_dir)
    if not directory.is_absolute():
        directory = Path(root).resolve() / directory
    directory.mkdir(parents=True, exist_ok=True)
    span = f"{chapters[0].article_id}-{chapters[-1].article_id}"
    stories = build_story_pdf(
        directory / f"{prefix}_Stories.pdf", project, chapters,
        title=f"{prefix} Stories {span}",
        subtitle=f"{len(chapters)} chapters · {span} · colour-cartridge edition",
    )
    exercises = build_exercise_pdf(
        directory / f"{prefix}_Exercises.pdf", chapters,
        title=f"{prefix} Exercises {span}",
    )
    answers = build_answer_pdf(
        directory / f"{prefix}_Answer_Key.pdf", chapters,
        title=f"{prefix} Answer Key {span}",
    )
    return {
        "story_pdf": str(stories),
        "exercise_pdf": str(exercises),
        "answer_pdf": str(answers),
        "chapters": len(chapters),
        "chapter_ids": [chapter.article_id for chapter in chapters],
    }


def build_chapter_pdfs(
    root: str | Path,
    chapters: Sequence[Chapter],
    out_dir: str | Path,
) -> list[dict[str, str]]:
    """Render one story, one exercise, and one answer PDF per chapter."""

    project = load_project(root)
    directory = Path(out_dir)
    if not directory.is_absolute():
        directory = Path(root).resolve() / directory
    directory.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, str]] = []
    for chapter in chapters:
        article_id = chapter.article_id
        story = build_story_pdf(
            directory / f"{article_id}_Story.pdf", project, [chapter],
            title=f"{article_id} {chapter.english_title}",
        )
        exercises = build_exercise_pdf(
            directory / f"{article_id}_Exercises.pdf", [chapter],
            title=f"{article_id} Exercises",
        )
        answers = build_answer_pdf(
            directory / f"{article_id}_Answer_Key.pdf", [chapter],
            title=f"{article_id} Answer Key",
        )
        written.append({
            "article_id": article_id,
            "story_pdf": str(story),
            "exercise_pdf": str(exercises),
            "answer_pdf": str(answers),
        })
    return written


def build_preview(
    root: str | Path,
    *,
    selector: str = "completed",
    out_dir: str | Path = DEFAULT_PREVIEW_DIR,
    prefix: str = "CET4_Preview",
    per_chapter: bool = True,
) -> dict[str, Any]:
    """Render the currently available chapters for immediate review."""

    chapters = select_chapters(root, selector)
    if not chapters:
        raise PdfBuildError("no chapters are available to render")
    volume = build_volume_pdfs(root, chapters, out_dir, prefix=prefix)
    result: dict[str, Any] = {"volume": volume}
    if per_chapter:
        result["per_chapter"] = build_chapter_pdfs(root, chapters, out_dir)
    return result


__all__ = [
    "DEFAULT_PREVIEW_DIR",
    "PdfBuildError",
    "build_answer_pdf",
    "build_chapter_pdfs",
    "build_exercise_pdf",
    "build_preview",
    "build_story_pdf",
    "build_volume_pdfs",
    "load_chapters",
    "select_chapters",
]
