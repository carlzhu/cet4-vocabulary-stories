"""Contract tests for auditable vocabulary matching in English story prose."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "source"))
matching = import_module("cet4_story.matching")

find_story_matches = matching.find_story_matches
match_vocabulary = matching.match_vocabulary


def _chapter(*paragraphs: str, **extra: Any) -> dict[str, object]:
    chapter: dict[str, object] = {
        "article_id": "CH001",
        "english_paragraphs": list(paragraphs),
    }
    chapter.update(extra)
    return chapter


def test_exact_form_is_case_insensitive_and_auditable() -> None:
    chapter = _chapter("The ABANDON order surprised everyone. A second abandon followed.")

    occurrence = match_vocabulary(
        chapter,
        vocabulary_id="V0001",
        lemma="abandon",
        include_uncertain_derivations=False,
    )

    assert occurrence.status == "verified"
    assert occurrence.occurrence_count == 2
    assert occurrence.original_form == "abandon"
    assert occurrence.matched_form == "ABANDON"
    assert occurrence.match_method == "exact"
    assert occurrence.context_sentence == "The ABANDON order surprised everyone."
    assert occurrence.paragraph_index == 1


def test_explicit_common_inflections_are_verified_from_ecdict() -> None:
    chapter = _chapter(
        "She abandons the plan, abandoned the cart, and is abandoning the route."
    )

    matches = find_story_matches(
        chapter,
        "abandon",
        "3:abandons/p:abandoned/i:abandoning",
        include_uncertain_derivations=False,
    )

    assert [match.matched_form for match in matches] == [
        "abandons",
        "abandoned",
        "abandoning",
    ]
    assert {match.match_method for match in matches} == {"ecdict_exchange"}
    assert {match.status for match in matches} == {"verified"}
    assert all("Explicit ECDICT exchange form" in match.review_note for match in matches)


def test_multiword_phrase_requires_the_complete_entry() -> None:
    chapter = _chapter(
        "In fact, the first clue mattered. The report was in factual agreement. "
        "Later, in\n\tfact, everyone agreed."
    )

    matches = find_story_matches(
        chapter,
        "in fact",
        include_uncertain_derivations=False,
    )

    assert [match.matched_form for match in matches] == ["In fact", "in\n\tfact"]
    assert all(match.canonical_form == "in fact" for match in matches)


@pytest.mark.parametrize(
    "paragraph",
    [
        "(signal), then silence.",
        'She called it "signal"!',
        "Was it signal? Yes.",
        "A signal—brief but clear—arrived.",
    ],
)
def test_punctuation_forms_valid_whole_entry_boundaries(paragraph: str) -> None:
    matches = find_story_matches(
        _chapter(paragraph),
        "signal",
        include_uncertain_derivations=False,
    )

    assert len(matches) == 1
    assert matches[0].matched_form == "signal"
    assert "signal" in matches[0].context_sentence


def test_substrings_and_hyphenated_compounds_do_not_match() -> None:
    chapter = _chapter(
        "The cart, artist, partial result, and art-like motif are not the entry."
    )

    occurrence = match_vocabulary(
        chapter,
        vocabulary_id="V0042",
        lemma="art",
        include_uncertain_derivations=False,
    )

    assert occurrence.status == "needs_revision"
    assert occurrence.occurrence_count == 0
    assert occurrence.matched_form is None
    assert occurrence.match_method is None
    assert occurrence.context_sentence is None
    assert occurrence.review_note == (
        "No whole-entry match was found in English story paragraphs."
    )


def test_uncertain_derivation_requires_revision_and_can_be_disabled() -> None:
    chapter = _chapter("They planned the route before dawn.")

    matches = find_story_matches(chapter, "plan")
    disabled_matches = find_story_matches(
        chapter,
        "plan",
        include_uncertain_derivations=False,
    )

    assert len(matches) == 1
    assert matches[0].matched_form == "planned"
    assert matches[0].canonical_form == "planned"
    assert matches[0].match_method == "derived"
    assert matches[0].status == "needs_revision"
    assert "manual review is required" in matches[0].review_note
    assert disabled_matches == ()


def test_non_story_sections_are_excluded_from_coverage() -> None:
    chapter = _chapter(
        "The approved prose contains no target entry.",
        english_title="Signal at Dawn",
        chinese_title="黎明信号",
        glossary=[{"word": "signal", "definition": "a sign"}],
        exercises=[
            {
                "id": "CH001-Q1",
                "prompt": "Which signal appeared?",
                "options": ["signal", "silence"],
            }
        ],
        answers=[
            {
                "id": "CH001-Q1",
                "answer": "signal",
                "explanation": "The signal appears in the exercise only.",
            }
        ],
        appendices=["signal signal signal"],
    )

    matches = find_story_matches(
        chapter,
        "signal",
        include_uncertain_derivations=False,
    )
    occurrence = match_vocabulary(
        chapter,
        vocabulary_id="V0100",
        lemma="signal",
        include_uncertain_derivations=False,
    )

    assert matches == ()
    assert occurrence.occurrence_count == 0
    assert occurrence.status == "needs_revision"
