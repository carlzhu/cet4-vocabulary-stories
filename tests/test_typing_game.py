"""The typing game page must stay in step with the protected vocabulary.

The page is generated, so these tests check the artefact rather than the generator:
that the embedded data parses, that it covers every chapter, and that the game logic
itself still works. The logic runs in Node because the game is JavaScript embedded in a
single HTML file; the check is skipped when Node is unavailable rather than failing, so
the suite stays runnable on a machine without it.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "CET4_Typing_Game.html"
TEMPLATE = PROJECT_ROOT / "game" / "template.html"
SMOKE = PROJECT_ROOT / "build" / "typing_game_smoke.mjs"
DATA_BLOCK = re.compile(
    r'<script id="word-data" type="application/json">(.*?)</script>', re.DOTALL
)


@pytest.fixture(scope="module")
def page() -> str:
    if not PAGE.is_file():
        pytest.skip("CET4_Typing_Game.html has not been generated")
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def payload(page: str) -> dict:
    match = DATA_BLOCK.search(page)
    assert match, "the page has no embedded word-data block"
    return json.loads(match.group(1))


def test_template_placeholders_are_substituted(page: str) -> None:
    for placeholder in ("__WORD_DATA__", "__TARGETS__", "__UNIQUE__", "__CHAPTERS__", "__ARCS__"):
        assert placeholder not in page


def test_embedded_words_match_the_protected_master(payload: dict) -> None:
    with (PROJECT_ROOT / "vocabulary_master.csv").open(encoding="utf-8-sig") as handle:
        master = list(csv.DictReader(handle))

    assert payload["targets"] == len(master) == 6127
    # A lemma may appear in more than one row; the page keeps one and drops the rest.
    assert payload["unique"] == len(payload["words"])
    assert payload["duplicates"] == len(master) - payload["unique"]

    lemmas = [word["w"].lower() for word in payload["words"]]
    assert len(lemmas) == len(set(lemmas)), "the page contains duplicate lemmas"
    master_lemmas = {row["lemma"].strip().lower() for row in master}
    assert set(lemmas) <= master_lemmas, "the page invented a lemma"


def test_every_chapter_and_arc_is_present(payload: dict) -> None:
    chapters = payload["chapters"]
    assert [c["n"] for c in chapters] == list(range(1, 138))

    per_chapter: dict[int, int] = {}
    for word in payload["words"]:
        per_chapter[word["c"]] = per_chapter.get(word["c"], 0) + 1
    assert set(per_chapter) == set(range(1, 138)), "a chapter has no words to practise"
    assert all(count > 0 for count in per_chapter.values())

    arcs = {word["a"] for word in payload["words"]}
    assert arcs == set(range(1, 11))
    assert all(1 <= c["a"] <= 10 for c in chapters)


def test_every_word_is_playable(payload: dict) -> None:
    typeable = re.compile(r"[A-Za-z' -]+")
    phrases = 0
    for word in payload["words"]:
        assert word["w"].strip(), "a word has an empty lemma"
        assert word["m"].strip(), f"{word['w']} has no gloss"
        # Typing reaches the game as letters, apostrophes, hyphens and - for the 14
        # phrase entries such as "ice cream" - a space. Anything else could never be
        # completed, because no keystroke would produce it.
        assert typeable.fullmatch(word["w"]), f"{word['w']} is untypeable"
        assert len(word["m"]) <= 36, f"{word['w']} has an over-long gloss"
        if " " in word["w"]:
            phrases += 1
    assert phrases == 14, f"expected 14 phrase entries, found {phrases}"


def test_script_tag_cannot_be_closed_by_the_data(page: str) -> None:
    """A lemma or gloss containing "</script>" would end the data block early."""

    match = DATA_BLOCK.search(page)
    assert match
    raw = match.group(1)
    assert "<" not in raw.replace("\\u003c", ""), "unescaped '<' inside the JSON block"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_game_logic_smoke_test_passes() -> None:
    if not SMOKE.is_file():
        pytest.skip("the smoke test script is missing")
    result = subprocess.run(
        ["node", str(SMOKE), str(PAGE)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "logic checks passed" in result.stdout


def test_template_is_the_source_of_the_page(page: str) -> None:
    """The committed page must come from the committed template, not from an old build."""

    template = TEMPLATE.read_text(encoding="utf-8")
    # The template holds the placeholders the generator replaces; the page must keep
    # everything else, so a stale page that predates a template edit fails here.
    for marker in ("const Core", "Core.keystroke", "pool-chapter", "review-list"):
        assert marker in template and marker in page, f"{marker} missing from template or page"
