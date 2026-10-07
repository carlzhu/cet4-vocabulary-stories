"""Auditable vocabulary matching for English story paragraphs.

Matching is deliberately conservative: entries are matched case-insensitively at
whole-entry boundaries, multiword entries must appear as the complete phrase,
and dictionary inflections are accepted only when explicitly listed by ECDICT.
A small morphology fallback is available for audit visibility, but every such
match is classified ``needs_revision`` rather than silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal, Mapping, Sequence

from .models import Chapter, CoverageKind, CoverageOccurrence, CoverageStatus

MatchMethod = Literal["exact", "ecdict_exchange", "derived"]

# ECDICT exchange codes documented by the source dictionary. Unknown codes are
# still retained as evidence, but are not safe enough for automatic approval.
ECDICT_EXCHANGE_CODES: Mapping[str, str] = {
    "0": "lemma",
    "1": "prototype",
    "3": "third_person_singular",
    "d": "past_participle",
    "i": "present_participle",
    "p": "past_tense",
    "r": "comparative",
    "s": "plural",
    "t": "superlative",
}

_WORD_EDGE = r"[\w\-'’]"
_SENTENCE_END = frozenset(".!?。！？")
_CLOSING_PUNCTUATION = frozenset("\"'”’)]}）】」』")


class MatchingError(ValueError):
    """The matcher received malformed vocabulary or story data."""


@dataclass(frozen=True, slots=True)
class ExchangeForm:
    """One form parsed from an ECDICT ``exchange`` cell."""

    form: str
    code: str
    relation: str
    certain: bool


@dataclass(frozen=True, slots=True)
class MatchForm:
    """A searchable form and the audit decision attached to it."""

    form: str
    method: MatchMethod
    status: CoverageStatus
    review_note: str | None = None


@dataclass(frozen=True, slots=True)
class VocabularyMatch:
    """One non-overlapping match in an English story paragraph."""

    matched_form: str
    canonical_form: str
    paragraph_index: int
    start: int
    end: int
    context_sentence: str
    match_method: MatchMethod
    status: CoverageStatus
    review_note: str | None = None

    def __post_init__(self) -> None:
        if self.paragraph_index < 1:
            raise MatchingError("paragraph index must be positive")
        if self.start < 0 or self.end <= self.start:
            raise MatchingError("match span must be non-empty")
        if not self.matched_form or not self.canonical_form:
            raise MatchingError("match forms must not be blank")
        if not self.context_sentence:
            raise MatchingError("context sentence must not be blank")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise MatchingError(f"{label} must not be blank")
    return value


def _split_exchange_values(raw: str) -> tuple[str, ...]:
    """Split one exchange value without changing the recorded word forms."""

    # ECDICT normally stores one form per code. Some exports contain comma- or
    # semicolon-separated alternatives, so support those explicit separators.
    values = re.split(r"\s*[,;|]\s*", raw)
    return tuple(value.strip() for value in values if value.strip())


def parse_ecdict_exchange(exchange: str | None) -> tuple[ExchangeForm, ...]:
    """Parse an ECDICT exchange cell into deduplicated explicit forms.

    Malformed non-empty segments are rejected: accepting them as prose would
    create unauditable false positives.
    """

    if exchange is None:
        return ()
    if not isinstance(exchange, str):
        raise TypeError("ecdict_exchange must be a string or None")
    if not exchange.strip():
        return ()

    parsed: list[ExchangeForm] = []
    seen: set[str] = set()
    for segment in exchange.split("/"):
        segment = segment.strip()
        if not segment:
            continue
        if ":" not in segment:
            raise MatchingError(
                f"invalid ECDICT exchange segment {segment!r}; expected code:form"
            )
        code, raw_forms = segment.split(":", 1)
        code = code.strip()
        if not code:
            raise MatchingError(f"invalid ECDICT exchange segment {segment!r}")
        forms = _split_exchange_values(raw_forms)
        if not forms:
            # Some ECDICT exports contain empty segments such as "i:" or "p:".
            # They carry no word form and must not abort coverage generation.
            continue
        relation = ECDICT_EXCHANGE_CODES.get(code, f"unknown_code_{code}")
        certain = code in ECDICT_EXCHANGE_CODES
        for form in forms:
            key = form.casefold()
            if key in seen:
                continue
            seen.add(key)
            parsed.append(
                ExchangeForm(
                    form=form,
                    code=code,
                    relation=relation,
                    certain=certain,
                )
            )
    return tuple(parsed)


def expand_ecdict_exchange(
    lemma: str, ecdict_exchange: str | None
) -> tuple[str, ...]:
    """Return explicit exchange forms, excluding case-only copies of ``lemma``."""

    canonical = _required_text(lemma, "lemma").casefold()
    return tuple(
        item.form
        for item in parse_ecdict_exchange(ecdict_exchange)
        if item.form.casefold() != canonical
    )


def _uncertain_derived_forms(lemma: str) -> tuple[str, ...]:
    """Generate visible fallback candidates; none are automatically verified."""

    if " " in lemma or not re.fullmatch(r"[A-Za-z]+", lemma):
        return ()

    lower = lemma.casefold()
    forms: set[str] = set()
    if lower.endswith("y") and len(lower) > 2 and lower[-2] not in "aeiou":
        stem = lower[:-1]
        forms.update((stem + "ies", stem + "ied"))
    elif lower.endswith(("s", "x", "z", "ch", "sh")):
        forms.add(lower + "es")
    else:
        forms.add(lower + "s")

    if lower.endswith("e"):
        forms.update((lower + "d", lower[:-1] + "ing"))
    else:
        forms.update((lower + "ed", lower + "ing"))

    # Include common final-consonant doubling as an uncertain candidate. It is
    # intentionally not treated as linguistically authoritative.
    if (
        len(lower) >= 3
        and lower[-1] not in "aeiouwxy"
        and lower[-2] in "aeiou"
        and lower[-3] not in "aeiou"
    ):
        forms.update((lower + lower[-1] + "ed", lower + lower[-1] + "ing"))

    forms.discard(lower)
    return tuple(sorted(forms))


def build_match_forms(
    lemma: str,
    ecdict_exchange: str | None = None,
    *,
    include_uncertain_derivations: bool = True,
) -> tuple[MatchForm, ...]:
    """Build priority-ordered exact, ECDICT, and uncertain search forms."""

    lemma = _required_text(lemma, "lemma")
    forms: list[MatchForm] = [MatchForm(lemma, "exact", "verified")]
    seen = {lemma.casefold()}

    for exchange_form in parse_ecdict_exchange(ecdict_exchange):
        key = exchange_form.form.casefold()
        if key in seen:
            continue
        seen.add(key)
        if exchange_form.certain:
            forms.append(
                MatchForm(
                    exchange_form.form,
                    "ecdict_exchange",
                    "verified",
                    (
                        "Explicit ECDICT exchange form "
                        f"({exchange_form.code}:{exchange_form.relation})."
                    ),
                )
            )
        else:
            forms.append(
                MatchForm(
                    exchange_form.form,
                    "ecdict_exchange",
                    "needs_revision",
                    f"ECDICT exchange code {exchange_form.code!r} is not recognized.",
                )
            )

    if include_uncertain_derivations:
        for derived in _uncertain_derived_forms(lemma):
            key = derived.casefold()
            if key in seen:
                continue
            seen.add(key)
            forms.append(
                MatchForm(
                    derived,
                    "derived",
                    "needs_revision",
                    "Form was inferred morphologically and is absent from "
                    "ecdict_exchange; manual review is required.",
                )
            )

    method_priority = {"exact": 0, "ecdict_exchange": 1, "derived": 2}
    return tuple(
        sorted(
            forms,
            key=lambda item: (
                method_priority[item.method],
                -len(item.form),
                item.form.casefold(),
            ),
        )
    )


def _entry_pattern(entry: str) -> re.Pattern[str]:
    """Compile a whole-entry expression while preserving multiword structure."""

    entry = _required_text(entry, "match form")
    pieces = re.split(r"\s+", entry)
    body = r"\s+".join(re.escape(piece) for piece in pieces)
    return re.compile(
        rf"(?<!{_WORD_EDGE}){body}(?!{_WORD_EDGE})",
        flags=re.IGNORECASE,
    )


def sentence_spans(paragraph: str) -> tuple[tuple[int, int], ...]:
    """Return trimmed sentence spans without rewriting the source paragraph."""

    if not isinstance(paragraph, str):
        raise TypeError("paragraph must be a string")
    spans: list[tuple[int, int]] = []
    cursor = 0
    length = len(paragraph)
    index = 0
    while index < length:
        if paragraph[index] not in _SENTENCE_END:
            index += 1
            continue
        end = index + 1
        while end < length and paragraph[end] in _CLOSING_PUNCTUATION:
            end += 1
        if end == length or paragraph[end].isspace():
            start = cursor
            while start < end and paragraph[start].isspace():
                start += 1
            trimmed_end = end
            while trimmed_end > start and paragraph[trimmed_end - 1].isspace():
                trimmed_end -= 1
            if start < trimmed_end:
                spans.append((start, trimmed_end))
            cursor = end
            while cursor < length and paragraph[cursor].isspace():
                cursor += 1
            index = cursor
        else:
            index = end

    start = cursor
    while start < length and paragraph[start].isspace():
        start += 1
    end = length
    while end > start and paragraph[end - 1].isspace():
        end -= 1
    if start < end:
        spans.append((start, end))
    return tuple(spans)


def extract_context_sentence(
    paragraph: str, match_start: int, match_end: int | None = None
) -> str:
    """Extract the exact sentence containing a match span."""

    if not isinstance(match_start, int) or isinstance(match_start, bool):
        raise TypeError("match_start must be an integer")
    if match_end is None:
        match_end = match_start + 1
    if not isinstance(match_end, int) or isinstance(match_end, bool):
        raise TypeError("match_end must be an integer")
    if match_start < 0 or match_end <= match_start or match_end > len(paragraph):
        raise MatchingError("match span is outside the paragraph")

    for start, end in sentence_spans(paragraph):
        if start <= match_start < end and match_end <= end:
            return paragraph[start:end]
    raise MatchingError("match span does not belong to a context sentence")


def story_paragraphs(chapter: Chapter | Mapping[str, object]) -> tuple[str, ...]:
    """Return only English story prose, excluding metadata and exercises."""

    if isinstance(chapter, Chapter):
        paragraphs: object = chapter.english_paragraphs
    elif isinstance(chapter, Mapping):
        if "english_paragraphs" not in chapter:
            raise MatchingError("chapter is missing english_paragraphs")
        paragraphs = chapter["english_paragraphs"]
    else:
        raise TypeError("chapter must be a Chapter or mapping")

    if isinstance(paragraphs, (str, bytes)) or not isinstance(paragraphs, Sequence):
        raise TypeError("english_paragraphs must be an array of strings")
    result: list[str] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        if not isinstance(paragraph, str):
            raise TypeError(f"english_paragraphs[{index - 1}] must be a string")
        if not paragraph.strip():
            raise MatchingError(f"english paragraph {index} must not be blank")
        result.append(paragraph)
    return tuple(result)


def find_story_matches(
    chapter: Chapter | Mapping[str, object],
    lemma: str,
    ecdict_exchange: str | None = None,
    *,
    include_uncertain_derivations: bool = True,
    scope: Literal["story"] = "story",
) -> tuple[VocabularyMatch, ...]:
    """Find non-overlapping entry matches in English story paragraphs only."""

    if scope != "story":
        raise MatchingError("only the story scope is permitted")
    candidates = build_match_forms(
        lemma,
        ecdict_exchange,
        include_uncertain_derivations=include_uncertain_derivations,
    )
    patterns = tuple((candidate, _entry_pattern(candidate.form)) for candidate in candidates)
    matches: list[VocabularyMatch] = []

    for paragraph_index, paragraph in enumerate(story_paragraphs(chapter), start=1):
        proposed: list[tuple[int, int, int, MatchForm, str]] = []
        for priority, (candidate, pattern) in enumerate(patterns):
            for match in pattern.finditer(paragraph):
                proposed.append(
                    (match.start(), match.end(), priority, candidate, match.group(0))
                )

        # Prefer the highest-confidence candidate when forms overlap, then the
        # longest span. This prevents one occurrence being counted twice.
        proposed.sort(key=lambda item: (item[0], item[2], -(item[1] - item[0])))
        accepted_spans: list[tuple[int, int]] = []
        for start, end, _, candidate, matched_text in proposed:
            if any(start < used_end and end > used_start for used_start, used_end in accepted_spans):
                continue
            accepted_spans.append((start, end))
            matches.append(
                VocabularyMatch(
                    matched_form=matched_text,
                    canonical_form=candidate.form,
                    paragraph_index=paragraph_index,
                    start=start,
                    end=end,
                    context_sentence=extract_context_sentence(paragraph, start, end),
                    match_method=candidate.method,
                    status=candidate.status,
                    review_note=candidate.review_note,
                )
            )

    return tuple(
        sorted(matches, key=lambda item: (item.paragraph_index, item.start, item.end))
    )


def match_vocabulary(
    chapter: Chapter | Mapping[str, object],
    *,
    vocabulary_id: str,
    lemma: str,
    ecdict_exchange: str | None = None,
    exchange: str | None = None,
    kind: CoverageKind = "new",
    include_uncertain_derivations: bool = True,
    scope: Literal["story"] = "story",
) -> CoverageOccurrence:
    """Summarize all story matches as an auditable coverage occurrence.

    ``exchange`` is a compatibility alias for source rows whose protected
    column retains the original ECDICT name. Passing both aliases is rejected.
    """

    vocabulary_id = _required_text(vocabulary_id, "vocabulary id")
    lemma = _required_text(lemma, "lemma")
    if ecdict_exchange is not None and exchange is not None:
        raise MatchingError("pass either ecdict_exchange or exchange, not both")
    exchange_value = ecdict_exchange if ecdict_exchange is not None else exchange
    matches = find_story_matches(
        chapter,
        lemma,
        exchange_value,
        include_uncertain_derivations=include_uncertain_derivations,
        scope=scope,
    )
    article_id = (
        chapter.article_id
        if isinstance(chapter, Chapter)
        else _required_text(chapter.get("article_id"), "article id")
    )

    if not matches:
        return CoverageOccurrence(
            vocabulary_id=vocabulary_id,
            lemma=lemma,
            article_id=article_id,
            status="needs_revision",
            occurrence_count=0,
            original_form=lemma,
            matched_form=None,
            match_method=None,
            context_sentence=None,
            review_note="No whole-entry match was found in English story paragraphs.",
            kind=kind,
            paragraph_index=None,
        )

    # A certain occurrence settles coverage even when an uncertain derived form
    # also appears in the story: the spec keeps *uncertain derivations* under
    # review, it does not let them invalidate an exact whole-entry occurrence.
    certain = tuple(match for match in matches if match.status != "needs_revision")
    if certain:
        chosen = certain[0]
        status: CoverageStatus = "verified"
        occurrence_count = len(certain)
    else:
        chosen = matches[0]
        status = "needs_revision"
        occurrence_count = len(matches)
    return CoverageOccurrence(
        vocabulary_id=vocabulary_id,
        lemma=lemma,
        article_id=article_id,
        status=status,
        occurrence_count=occurrence_count,
        original_form=lemma,
        matched_form=chosen.matched_form,
        match_method=chosen.match_method,
        context_sentence=chosen.context_sentence,
        review_note=chosen.review_note,
        kind=kind,
        paragraph_index=chosen.paragraph_index,
    )


def match_vocabulary_record(
    chapter: Chapter | Mapping[str, object],
    record: Mapping[str, str],
    *,
    id_field: str = "vocabulary_id",
    lemma_field: str = "word",
    exchange_field: str = "exchange",
    kind: CoverageKind = "new",
) -> CoverageOccurrence:
    """Match one immutable vocabulary source row without altering its values."""

    try:
        vocabulary_id = record[id_field]
        lemma = record[lemma_field]
    except KeyError as exc:
        raise MatchingError(f"vocabulary record is missing {exc.args[0]!r}") from exc
    if exchange_field in record:
        exchange = record[exchange_field]
    elif exchange_field == "exchange" and "ecdict_exchange" in record:
        exchange = record["ecdict_exchange"]
    else:
        exchange = ""
    return match_vocabulary(
        chapter,
        vocabulary_id=vocabulary_id,
        lemma=lemma,
        ecdict_exchange=exchange,
        kind=kind,
    )


def match_chapter_vocabulary(
    chapter: Chapter | Mapping[str, object],
    records: Iterable[Mapping[str, str]],
    *,
    kind: CoverageKind = "new",
) -> tuple[CoverageOccurrence, ...]:
    """Match source rows in input order against the chapter's story prose."""

    return tuple(match_vocabulary_record(chapter, record, kind=kind) for record in records)


# Readable aliases for downstream validators and reports.
find_vocabulary_occurrences = find_story_matches
extract_story_paragraphs = story_paragraphs

__all__ = [
    "ECDICT_EXCHANGE_CODES",
    "ExchangeForm",
    "MatchForm",
    "MatchMethod",
    "MatchingError",
    "VocabularyMatch",
    "build_match_forms",
    "expand_ecdict_exchange",
    "extract_context_sentence",
    "extract_story_paragraphs",
    "find_story_matches",
    "find_vocabulary_occurrences",
    "match_chapter_vocabulary",
    "match_vocabulary",
    "match_vocabulary_record",
    "parse_ecdict_exchange",
    "sentence_spans",
    "story_paragraphs",
]
