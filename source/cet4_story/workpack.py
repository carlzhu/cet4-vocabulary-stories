"""Compact, auditable work packets for generating the remaining chapters.

A packet carries exactly the protected plan fields plus the mandated target
words and their auditable meanings, so chapter writing never has to guess what
must appear.  The packet is derived state only: nothing here is written back to
a protected source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from cet4_story.batch import (
    completed_chapter_ids,
    continuity_path,
    next_batch_chapter_ids,
    ordered_chapter_ids,
)
from cet4_story.continuity import load_continuity
from cet4_story.models import ContinuityState
from cet4_story.project_data import ProjectData

MEANING_LIMIT = 26
_ID_SPLIT = re.compile(r"[;|,]")


class WorkpackError(ValueError):
    """A work packet could not be derived from the protected sources."""


def split_plan_ids(value: str) -> tuple[str, ...]:
    """Split a protected plan id list that uses ``;``, ``|``, or ``,``."""

    if not value:
        return ()
    return tuple(part.strip() for part in _ID_SPLIT.split(value) if part.strip())


def short_meaning(value: str, limit: int = MEANING_LIMIT) -> str:
    """Collapse an ECDICT translation into one short, printable gloss."""

    if not value:
        return ""
    first_line = value.splitlines()[0].strip()
    first_line = first_line.split("\\n")[0].strip()
    if len(first_line) <= limit:
        return first_line
    return first_line[: limit - 1].rstrip(" ,;，、") + "…"


@dataclass(frozen=True, slots=True)
class WordRequirement:
    """One mandated occurrence target for a chapter."""

    vocabulary_id: str
    lemma: str
    kind: str
    chinese_meaning: str = ""
    introduced_in: str | None = None

    def render(self) -> str:
        meaning = short_meaning(self.chinese_meaning)
        origin = f"[{self.introduced_in}]" if self.introduced_in else ""
        if meaning:
            return f"{self.lemma}({meaning}){origin}"
        return f"{self.lemma}{origin}"


@dataclass(frozen=True, slots=True)
class ChapterWorkpack:
    """Everything needed to write and check one chapter."""

    article_id: str
    chapter_number: int
    english_title: str
    chinese_title: str
    theme: str
    plot_summary: str
    status: str
    arc_number: int
    story_day: int
    estimated_story_words: int
    new_words: tuple[WordRequirement, ...]
    review_words: tuple[WordRequirement, ...] = ()

    def render(self) -> str:
        lines = [
            f"{self.article_id} | {self.english_title} | {self.chinese_title} | {self.theme}",
            (
                f"  plan: words~{self.estimated_story_words} arc={self.arc_number} "
                f"day={self.story_day} status={self.status}"
            ),
            f"  plot: {self.plot_summary}",
            f"  new[{len(self.new_words)}]: "
            + " | ".join(word.render() for word in self.new_words),
        ]
        lines.append(
            f"  review[{len(self.review_words)}]: "
            + (" | ".join(word.render() for word in self.review_words) or "-")
        )
        return "\n".join(lines)


def _introduced_by(project: ProjectData) -> dict[str, str]:
    introduced: dict[str, str] = {}
    for chapter_id, vocabulary_ids in project.source.new_vocabulary_ids_by_chapter.items():
        for vocabulary_id in vocabulary_ids:
            introduced[vocabulary_id] = chapter_id
    return introduced


def _requirement(
    project: ProjectData,
    vocabulary_id: str,
    kind: str,
    introduced: Mapping[str, str],
) -> WordRequirement:
    try:
        record = project.vocabulary_by_id[vocabulary_id]
    except KeyError as exc:
        raise WorkpackError(f"plan references unknown target {vocabulary_id!r}") from exc
    lemma = record.get("lemma", "").strip()
    if not lemma:
        raise WorkpackError(f"target {vocabulary_id!r} has no lemma")
    return WordRequirement(
        vocabulary_id=vocabulary_id,
        lemma=lemma,
        kind=kind,
        chinese_meaning=record.get("chinese_meaning", "") or record.get("translation", ""),
        introduced_in=introduced.get(vocabulary_id) if kind == "review" else None,
    )


def chapter_workpack(project: ProjectData, chapter_id: str) -> ChapterWorkpack:
    """Build the generation packet for one planned chapter."""

    try:
        plan = project.source.chapter_record(chapter_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkpackError(f"unknown chapter {chapter_id!r}") from exc
    introduced = _introduced_by(project)
    allocation = project.source.new_vocabulary_ids_by_chapter
    new_ids = allocation.get(chapter_id)
    if new_ids is None:
        raise WorkpackError(f"no allocation recorded for {chapter_id!r}")

    review_ids = split_plan_ids(plan.get("review_vocabulary_ids", ""))
    return ChapterWorkpack(
        article_id=chapter_id,
        chapter_number=int(plan.get("chapter_number", 0) or 0),
        english_title=plan.get("english_title", ""),
        chinese_title=plan.get("chinese_title", ""),
        theme=plan.get("theme", ""),
        plot_summary=plan.get("plot_summary", ""),
        status=plan.get("status", ""),
        arc_number=int(plan.get("arc_number", 0) or 0),
        story_day=int(plan.get("story_day", 0) or 0),
        estimated_story_words=int(plan.get("estimated_story_words", 0) or 0),
        new_words=tuple(
            _requirement(project, vocabulary_id, "new", introduced)
            for vocabulary_id in new_ids
        ),
        review_words=tuple(
            _requirement(project, vocabulary_id, "review", introduced)
            for vocabulary_id in review_ids
        ),
    )


def batch_workpack(
    project: ProjectData, chapter_ids: Sequence[str]
) -> tuple[ChapterWorkpack, ...]:
    return tuple(chapter_workpack(project, chapter_id) for chapter_id in chapter_ids)


def resolve_chapter_ids(project: ProjectData, selector: str) -> tuple[str, ...]:
    """Resolve ``next``, ``CH002``, or ``CH002-CH009`` into chapter ids."""

    text = selector.strip().upper()
    if text in {"NEXT", ""}:
        return next_batch_chapter_ids(completed_chapter_ids(project.root))
    if "-" in text:
        start, _, end = text.partition("-")
        start = start if start.startswith("CH") else f"CH{start}"
        end = end if end.startswith("CH") else f"CH{end}"
        known = ordered_chapter_ids()
        if start not in known or end not in known:
            raise WorkpackError(f"unknown chapter range {selector!r}")
        first = known.index(start)
        last = known.index(end)
        if last < first:
            raise WorkpackError(f"reversed chapter range {selector!r}")
        return known[first : last + 1]
    candidate = text if text.startswith("CH") else f"CH{text}"
    if candidate not in ordered_chapter_ids():
        raise WorkpackError(f"unknown chapter {selector!r}")
    return (candidate,)


def latest_boundary(project: ProjectData) -> ContinuityState | None:
    """Return the most recent recorded batch boundary, if any."""

    states = load_continuity(continuity_path(project.root))
    if not states:
        return None
    return max(states.values(), key=lambda state: state.chapter_id)


def render_boundary(state: ContinuityState | None) -> str:
    if state is None:
        return "continuity-in: none recorded yet (no batch boundary on file)"
    lines = [
        f"continuity-in (after {state.chapter_id}): {state.last_event}",
        f"  unresolved: {state.unresolved_consequence or '-'}",
        f"  next chapter must start from: {state.first_required_event_next_chapter or '-'}",
        f"  locations: {', '.join(f'{k}@{v}' for k, v in state.character_locations.items()) or '-'}",
        f"  roles: {', '.join(f'{k}={v}' for k, v in state.character_roles.items()) or '-'}",
        f"  open commitments: {'; '.join(state.open_commitments) or '-'}",
        f"  open conflicts: {'; '.join(state.open_conflicts) or '-'}",
        f"  established facts: {'; '.join(state.established_facts) or '-'}",
    ]
    return "\n".join(lines)


def render_batch_workpack(
    project: ProjectData,
    chapter_ids: Sequence[str],
    *,
    include_cast: bool = True,
) -> str:
    """Render the full generation brief for one batch."""

    parts: list[str] = []
    if include_cast:
        from cet4_story.continuity import parse_cast

        cast = parse_cast(project.source.character_guide)
        parts.append("cast: " + ", ".join(cast))
    parts.append(render_boundary(latest_boundary(project)))
    parts.append(f"batch: {chapter_ids[0]}-{chapter_ids[-1]} ({len(chapter_ids)} chapters)")
    parts.extend(pack.render() for pack in batch_workpack(project, chapter_ids))
    parts.append(
        "rules: 350-450 English words, 4-6 paragraphs, one Chinese paragraph per "
        "English paragraph, exactly 5 exercises and 5 answers with ids CHxxx-Q1..Q5, "
        "every mandated lemma must appear as a whole word in the English story only."
    )
    return "\n".join(parts)


__all__ = [
    "ChapterWorkpack",
    "WorkpackError",
    "WordRequirement",
    "batch_workpack",
    "chapter_workpack",
    "latest_boundary",
    "render_batch_workpack",
    "render_boundary",
    "resolve_chapter_ids",
    "short_meaning",
    "split_plan_ids",
]
