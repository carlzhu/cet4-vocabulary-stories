"""Tests for chapter selection in the generalized PDF builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from cet4_story.pdf_builder import PdfBuildError, load_chapters, select_chapters

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_completed_chapters_are_unique_and_ordered() -> None:
    chapters = load_chapters(PROJECT_ROOT)
    selected = [chapter.article_id for chapter in select_chapters(PROJECT_ROOT)]

    assert selected == sorted(selected)
    assert len(selected) == len(chapters)
    assert "CH001" in selected
    assert "CH002" in selected


def test_range_selection_returns_the_requested_window() -> None:
    selected = [chapter.article_id for chapter in select_chapters(PROJECT_ROOT, "CH002-CH004")]

    assert selected == ["CH002", "CH003", "CH004"]


def test_unknown_range_is_rejected() -> None:
    with pytest.raises(PdfBuildError):
        select_chapters(PROJECT_ROOT, "CH200-CH204")
