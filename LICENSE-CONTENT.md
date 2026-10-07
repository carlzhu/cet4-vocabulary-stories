# Licensing: what applies to which part of this repository

Two licenses, because the repository holds two kinds of work. `LICENSE` is the pure MIT
text and governs the software; this file governs the curriculum content.

| Scope | License |
|---|---|
| **Software** — `source/`, `tests/`, `build/`, `specs/`, `pyproject.toml`, `uv.lock` | **MIT** — see `LICENSE` |
| **Content** — the chapters, translations, exercises, answer key, manuscript, rendered PDFs, audio, video, and the explanatory documents | **CC BY 4.0** — this file |
| **Third-party data** — `data/cet4_metadata_subset.jsonl`, ECDICT-derived metadata | **MIT, Copyright (c) 2022 SmartCoding** — see `data/LICENSE.endict.txt` |

`LICENSE` deliberately contains nothing but the MIT text. An earlier version appended a
scope note to it, and GitHub's license detector then reported `NOASSERTION` instead of
MIT: the detector matches the license body and extra prose defeats it. The note lives
here instead, where it does no harm.

---

# Content license: Creative Commons Attribution 4.0 International (CC BY 4.0)

The curriculum content in this repository is licensed under the **Creative Commons
Attribution 4.0 International License (CC BY 4.0)**.

Copyright (c) 2026 carlzhu

## What this covers

- `drafts/batches/*.json` and `drafts/sample_chapters.json` - the 137 chapters
  (English story text and Chinese translations)
- `CET4_Vocabulary_Stories.pdf`, `CET4_Exercises.pdf`, `CET4_Answer_Key.pdf`
- `build/preview/` and `build/CET4_Sample_*.pdf` - the rendered volumes
- `build/audio/` - the chapter narration
- `build/video/` - the subtitled videos and their `.srt` files
- `CET4_Typing_Game.html` and `game/template.html` - the typing game page
- `reports/manuscript.md` - the assembled bilingual manuscript
- the explanatory documents: `README.md`, `BUILD_NOTES.md`, `quality_report.md`,
  `vocabulary_coverage_report.md`, `character_guide.md`, `story_timeline.md`,
  `layout_capacity.md`, `vocabulary_audit.md`

## You are free to

- **Share** - copy and redistribute the material in any medium or format
- **Adapt** - remix, transform, and build upon the material for any purpose,
  including commercially

## Under the following terms

- **Attribution** - You must give appropriate credit, provide a link to the
  license, and indicate if changes were made. You may do so in any reasonable
  manner, but not in any way that suggests the licensor endorses you or your use.
- **No additional restrictions** - You may not apply legal terms or technological
  measures that legally restrict others from doing anything the license permits.

## Attribution example

> "CET-4 Vocabulary Stories" by carlzhu, licensed under CC BY 4.0.
> Source: https://github.com/carlzhu/cet4-vocabulary-stories

## The legal code

The binding legal code is the canonical CC BY 4.0 text at
<https://creativecommons.org/licenses/by/4.0/legalcode>.

It is referenced rather than reproduced here deliberately: paraphrasing or
transcribing a license invites error, and CC BY 4.0 requires that the license
itself be linked and its terms followed, not that a copy be embedded. If you need
the full text vendored into this repository, add
`https://creativecommons.org/licenses/by/4.0/legalcode.txt` verbatim as
`LICENSE-CONTENT-legalcode.txt`.
