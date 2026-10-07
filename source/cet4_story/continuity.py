"""Batch-boundary continuity records and structural continuity checks.

The spec requires a recoverable continuity record at every batch boundary.  A
record is authored alongside the chapters; the deterministic checks here prove
that a later record never erases an established fact, never silently drops an
open commitment or conflict, and never introduces a character outside
``character_guide.md``.  Semantic review (does the prose really follow causally?)
remains a human task and is never claimed as automated coverage.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from cet4_story.models import ContinuityState

CONTINUITY_FILENAME = "continuity.json"
CONTINUITY_SCHEMA_VERSION = 1

_CAST_HEADING = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_NAME_SPLIT = re.compile(r"\s*[（(—–-]")


class ContinuityError(ValueError):
    """A continuity record is malformed or breaks an established fact."""


def parse_cast(character_guide: str) -> tuple[str, ...]:
    """Extract the character names from the level-3 headings of the guide."""

    names: list[str] = []
    for match in _CAST_HEADING.finditer(character_guide):
        name = _NAME_SPLIT.split(match.group(1).strip(), maxsplit=1)[0].strip()
        if name and name not in names:
            names.append(name)
    if not names:
        raise ContinuityError("character_guide.md declares no characters")
    return tuple(names)


def state_to_dict(state: ContinuityState) -> dict[str, Any]:
    """Serialize one boundary record in a stable, diff-friendly shape."""

    return {
        "chapter_id": state.chapter_id,
        "last_event": state.last_event,
        "unresolved_consequence": state.unresolved_consequence,
        "character_locations": dict(state.character_locations),
        "character_roles": dict(state.character_roles),
        "open_commitments": list(state.open_commitments),
        "open_conflicts": list(state.open_conflicts),
        "first_required_event_next_chapter": state.first_required_event_next_chapter,
        "established_facts": list(state.established_facts),
    }


def state_from_dict(value: object) -> ContinuityState:
    """Rebuild one boundary record, rejecting unknown keys."""

    if not isinstance(value, Mapping):
        raise ContinuityError("continuity record must be an object")
    allowed = set(ContinuityState.__dataclass_fields__)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ContinuityError(f"continuity record has unknown keys: {', '.join(unknown)}")
    try:
        return ContinuityState(
            chapter_id=value["chapter_id"],
            last_event=value["last_event"],
            unresolved_consequence=value.get("unresolved_consequence"),
            character_locations=dict(value.get("character_locations", {})),
            character_roles=dict(value.get("character_roles", {})),
            open_commitments=tuple(value.get("open_commitments", ())),
            open_conflicts=tuple(value.get("open_conflicts", ())),
            first_required_event_next_chapter=value.get(
                "first_required_event_next_chapter"
            ),
            established_facts=tuple(value.get("established_facts", ())),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContinuityError(f"invalid continuity record: {exc}") from exc


def _mentioned(text: str, phrases: Iterable[str]) -> list[str]:
    haystack = text.casefold()
    return [phrase for phrase in phrases if phrase.casefold() not in haystack]


def check_boundary(
    previous: ContinuityState | None,
    current: ContinuityState,
    *,
    cast: Sequence[str],
    expected_first_chapter: str | None = None,
) -> list[str]:
    """Return every structural continuity error for one batch boundary."""

    errors: list[str] = []
    if expected_first_chapter is not None and current.chapter_id != expected_first_chapter:
        errors.append(
            f"continuity record is for {current.chapter_id}, expected "
            f"{expected_first_chapter}"
        )
    if not current.first_required_event_next_chapter:
        errors.append(
            f"{current.chapter_id}: boundary must state the first required event of the "
            "next chapter"
        )

    known = {name.casefold() for name in cast}
    for label, mapping in (
        ("location", current.character_locations),
        ("role", current.character_roles),
    ):
        unknown = sorted(
            name for name in mapping if name.casefold() not in known
        )
        if unknown:
            errors.append(
                f"{current.chapter_id}: unknown character in {label} record: "
                + ", ".join(unknown)
            )

    if previous is None:
        return errors

    missing_facts = [
        fact for fact in previous.established_facts if fact not in current.established_facts
    ]
    if missing_facts:
        errors.append(
            f"{current.chapter_id}: established facts were dropped: "
            + "; ".join(missing_facts)
        )

    resolution_text = " ".join(
        part
        for part in (
            current.last_event,
            current.unresolved_consequence or "",
            *current.established_facts,
            *current.open_commitments,
            *current.open_conflicts,
        )
    )
    still_open = {
        *current.open_commitments,
        *current.open_conflicts,
    }
    for label, items in (
        ("commitment", previous.open_commitments),
        ("conflict", previous.open_conflicts),
    ):
        silent = [
            item
            for item in items
            if item not in still_open and _mentioned(resolution_text, (item,))
        ]
        if silent:
            errors.append(
                f"{current.chapter_id}: open {label}(s) neither carried forward nor "
                "explicitly resolved: " + "; ".join(silent)
            )

    if current.chapter_id <= previous.chapter_id:
        errors.append(
            f"{current.chapter_id}: boundary records must advance in chapter order "
            f"after {previous.chapter_id}"
        )
    return errors


def load_continuity(path: str | Path) -> Mapping[str, ContinuityState]:
    """Load boundary records keyed by their chapter id."""

    continuity_path = Path(path)
    if not continuity_path.is_file():
        return MappingProxyType({})
    document = json.loads(continuity_path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ContinuityError("continuity document must be an object")
    if document.get("schema_version") != CONTINUITY_SCHEMA_VERSION:
        raise ContinuityError("unsupported continuity schema version")
    boundaries = document.get("boundaries")
    if not isinstance(boundaries, list):
        raise ContinuityError("continuity document must list boundaries")

    states: dict[str, ContinuityState] = {}
    for entry in boundaries:
        state = state_from_dict(entry)
        if state.chapter_id in states:
            raise ContinuityError(f"duplicate continuity record for {state.chapter_id}")
        states[state.chapter_id] = state
    return MappingProxyType(states)


def save_continuity(
    path: str | Path, states: Mapping[str, ContinuityState] | Iterable[ContinuityState]
) -> Path:
    """Write boundary records ordered by chapter id."""

    continuity_path = Path(path)
    if isinstance(states, Mapping):
        ordered = sorted(states.values(), key=lambda state: state.chapter_id)
    else:
        ordered = sorted(states, key=lambda state: state.chapter_id)
    document = {
        "schema_version": CONTINUITY_SCHEMA_VERSION,
        "boundaries": [state_to_dict(state) for state in ordered],
    }
    continuity_path.parent.mkdir(parents=True, exist_ok=True)
    continuity_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return continuity_path


__all__ = [
    "CONTINUITY_FILENAME",
    "CONTINUITY_SCHEMA_VERSION",
    "ContinuityError",
    "check_boundary",
    "load_continuity",
    "parse_cast",
    "save_continuity",
    "state_from_dict",
    "state_to_dict",
]
