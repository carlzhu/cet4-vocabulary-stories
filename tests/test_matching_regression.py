"""Regression tests for coverage resolution in :mod:`cet4_story.matching`."""

from __future__ import annotations

import pytest

from cet4_story.matching import (
    MatchingError,
    match_vocabulary,
    parse_ecdict_exchange,
)


def test_empty_exchange_segments_are_skipped() -> None:
    """Real ECDICT exports contain segments such as ``i:`` with no form."""

    forms = parse_ecdict_exchange("p:walked/i:/d:walked/3:walks/s:")

    assert [form.form for form in forms] == ["walked", "walks"]


def test_segment_without_a_code_is_still_rejected() -> None:
    with pytest.raises(MatchingError):
        parse_ecdict_exchange("walked")


def test_certain_occurrence_outweighs_an_uncertain_derivation() -> None:
    """An exact whole-entry match settles coverage even for entries such as 'the'.

    Entries without ECDICT exchange data still produce uncertain derived
    candidates. Those candidates must not turn a present whole word into
    ``needs_revision``.
    """

    chapter = {
        "article_id": "CH001",
        "english_paragraphs": ["The map was on the table."],
    }

    occurrence = match_vocabulary(chapter, vocabulary_id="V-THE", lemma="the")

    assert occurrence.status == "verified"
    assert occurrence.match_method == "exact"
    assert occurrence.occurrence_count == 2
    assert occurrence.context_sentence


def test_missing_target_stays_needs_revision() -> None:
    chapter = {
        "article_id": "CH001",
        "english_paragraphs": ["A short sentence about a map."],
    }

    occurrence = match_vocabulary(chapter, vocabulary_id="V-ABSENT", lemma="zebra")

    assert occurrence.status == "needs_revision"
    assert occurrence.match_method is None
    assert occurrence.occurrence_count == 0
