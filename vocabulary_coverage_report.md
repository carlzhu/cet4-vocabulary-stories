# Vocabulary Coverage Report

Generated from the committed checkpoint (`drafts/batches/checkpoint.json`) and the
protected sources. Reproduce with:

```powershell
uv run cet4-stories --project-root "D:\files\stroy" audit-curriculum
```

## Final curriculum

- Unique target forms: 6,127
- Planned chapters: 137
- Allocated targets: 6,127
- Duplicate or missing allocations: 0
- Generated chapters: 137 (134 generated in batches + 3 preserved samples)
- Committed batches: 34
- **Verified new-story targets: 6,127 / 6,127**
- Targets needing revision: 0
- Uncovered targets: 0
- Contextual review occurrences assigned: 2,448
- Contextual review occurrences verified: 2,448

Per-target evidence is in `vocabulary_coverage.csv` (12 columns, 6,127 rows, one
row per target): `vocabulary_id`, `lemma`, `part_of_speech`,
`part_of_speech_source`, `phonetic`, `needs_review`, `chapter_id`,
`occurrence_count`, `status`, `matched_form`, `match_method`,
`context_sentence`.

## Matching policy

Coverage requires a real whole-entry occurrence in **English story text**. A
glossary, vocabulary table, exercise prompt, exercise option, title, or appendix
does not count, and neither does a substring: `across` never covers `cross`, and
`nap's` never covers `nap`. Inflected forms are accepted only through the ECDICT
`exchange` field for the entry and are recorded with their `matched_form` and
`match_method`, so a reviewer can see exactly which surface form satisfied the
requirement.

## Sample chapters

CH001, CH050, and CH090 were preserved rather than regenerated. CH090 needed one
substantive correction during this work: its earlier coverage claim of 45/45 was
produced by substring matching, and `cross` and `gene` appeared only inside
`across` and `gene-related`. The scene was rewritten so both lemmas occur as real
whole words, and the matching bug that allowed the false positive was fixed and
covered by a regression test.

## Human review status

Automated coverage is complete. **Human semantic review has not been performed
and is not claimed.** Two specific gaps limit what the automated checks can say:

- 41 targets have no part of speech from the protected CSV, the morphological
  inference, or ECDICT (`part_of_speech_source = missing`).
- 48 targets have no phonetic transcription.

Every protected vocabulary row carries `needs_review=yes`, so that field is a
global marker, not a per-item triage. Judging whether a chosen sentence is a
natural and pedagogically useful context for a lemma is a human decision that
this report cannot make.

## Translation status

The bilingual text is complete: all 738 paragraph pairs render their English
content in Chinese, and 0 fall below the calibrated density threshold of 1.2 CJK
characters per English word. 113 abridged paragraphs were rewritten to reach that
state. The 10 residual sentence-count differences are merges - Chinese rendering
two English sentences as one - and were each inspected by eye.
