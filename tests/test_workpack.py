"""Tests for the chapter generation work packets and the batch CLI surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from cet4_story.batch import completed_chapter_ids, next_batch_chapter_ids
from cet4_story.cli import build_parser
from cet4_story.project_data import PROVENANCE_PATH, load_project, write_provenance
from cet4_story.workpack import (
    WorkpackError,
    chapter_workpack,
    render_batch_workpack,
    render_boundary,
    resolve_chapter_ids,
    short_meaning,
    split_plan_ids,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def project():
    if not (PROJECT_ROOT / PROVENANCE_PATH).is_file():
        write_provenance(PROJECT_ROOT)
    return load_project(PROJECT_ROOT)


def test_resolve_chapter_ids(project) -> None:
    assert resolve_chapter_ids(project, "CH002") == ("CH002",)
    assert resolve_chapter_ids(project, "CH002-CH004") == ("CH002", "CH003", "CH004")

    expected_next = next_batch_chapter_ids(completed_chapter_ids(project.root))
    assert resolve_chapter_ids(project, "next") == expected_next

    # "next" must be the first eight still-unfinished chapters, in plan order.
    # It shrinks as the curriculum nears its end and is empty once every chapter
    # is committed, so assert the exact size rather than a fixed number.
    completed = set(completed_chapter_ids(project.root))
    remaining = [cid for cid in project.chapter_ids if cid not in completed]
    assert expected_next == tuple(remaining[:8])
    assert len(expected_next) == min(8, len(remaining))

    with pytest.raises(WorkpackError):
        resolve_chapter_ids(project, "CH999")
    with pytest.raises(WorkpackError):
        resolve_chapter_ids(project, "CH009-CH002")


def test_split_plan_ids() -> None:
    assert split_plan_ids("a|b;c,d") == ("a", "b", "c", "d")
    assert split_plan_ids("") == ()
    assert split_plan_ids("  a |  | b ") == ("a", "b")


def test_short_meaning_collapses_ecdict_translations() -> None:
    assert short_meaning("n. 能力") == "n. 能力"
    assert short_meaning("") == ""

    long = "n. " + "很长的释义" * 10
    collapsed = short_meaning(long)
    assert len(collapsed) <= 26
    assert collapsed.endswith("…")


def test_workpack_carries_every_mandated_word(project) -> None:
    pack = chapter_workpack(project, "CH002")
    allocation = project.source.new_vocabulary_ids_by_chapter["CH002"]

    assert pack.article_id == "CH002"
    assert pack.english_title
    assert pack.theme
    assert [word.vocabulary_id for word in pack.new_words] == list(allocation)
    assert len(pack.new_words) == 45
    assert len(pack.review_words) == 18
    assert all(word.lemma for word in pack.new_words)
    assert all(word.chinese_meaning for word in pack.new_words)
    assert all(word.introduced_in for word in pack.review_words)

    rendered = render_batch_workpack(project, ("CH002",))
    assert "CH002" in rendered
    assert "new[45]" in rendered
    assert "review[18]" in rendered
    assert "rules:" in rendered
    assert "continuity-in" in rendered


def test_boundary_render_without_history(project) -> None:
    assert "none recorded yet" in render_boundary(None)


def test_cli_parses_the_batch_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["--project-root", ".", "verify-sources"]).command == "verify-sources"
    assert parser.parse_args(["checkpoint-status"]).command == "checkpoint-status"

    next_args = parser.parse_args(["next-batch", "--size", "4"])
    assert next_args.command == "next-batch"
    assert next_args.size == 4

    work_args = parser.parse_args(["workpack", "next"])
    assert work_args.selector == "next"

    validate_args = parser.parse_args(["validate-batch", "drafts/batches/x.json"])
    assert validate_args.command == "validate-batch"
    assert validate_args.no_continuity is False
