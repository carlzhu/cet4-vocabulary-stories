# CET-4 Vocabulary Stories · 大学英语四级词汇故事集

A complete, verifiable **CET-4 vocabulary curriculum** built as one continuous
137-chapter bilingual (English / Chinese) story, with a vocabulary table, a page of
exercises, and an answer key for every chapter.

Every one of the **6,127 CET-4 target words** is placed in real narrative context
and machine-verified as a whole-word occurrence. All 137 chapters are committed,
validated, and rendered to print-ready A4 PDFs.

**Status: automated generation and validation are complete. Human semantic review
has *not* been performed — see [Limitations](#limitations) before using this
material to teach.**

---

## What is in this repository

| | |
|---|---|
| Chapters | **137 / 137**, in 10 narrative arcs |
| CET-4 targets placed and verified | **6,127 / 6,127** |
| Spaced-review occurrences verified | **2,448 / 2,448** |
| Bilingual paragraphs | **738** pairs, all rendered in Chinese |
| Exercises | 5 per chapter, `CHxxx-Q1` … `CHxxx-Q5`, with an answer key |
| Rendered PDFs | 501 + 137 + 20 pages, A4 |
| Tests | **94 passing**, `ruff` clean across `source/`, `tests/`, `build/` |

### The story

Ten arcs of 14 chapters each (arc 10 has 11), following one group through a
university access project, a research method, a family promise, a first real
deadline, a border, a body that will not rest, a system that remembers too much, a
river, a city budget, and finally a choice that has a cost. Each arc opener carries
an in-world recap of the previous arc and each arc closer an echo of its theme, so
the 137 chapters read as one continuous line rather than as unrelated units.

Chapter titles follow a fixed 14-beat rhythm, e.g. arc 2:
`A Signal → The First Promise → A Missing Voice → Evidence on the Table → The Trial
Run → Pressure Builds → The Disagreement → What the Numbers Hide → A Better
Question → The Second Attempt → Outside Pressure → The Decision → Consequences →
The Bridge Forward`.

### Chapter rules (enforced, not aspirational)

- 350–450 English words, 4–6 paragraphs, equal English/Chinese paragraph counts
- exactly 5 exercises and 5 answers per chapter
- exercise prompts may not leak their own answers
- every planned target must appear as a whole word — substrings do not count
- every paragraph must render its English content in Chinese at ≥ 1.2 CJK
  characters per English word (this corpus's faithful renderings run at a median
  of 1.48)

---

## Deliverables

At the repository root:

| File | Contents |
|---|---|
| `CET4_Vocabulary_Stories.pdf` | 501 pages: 137 stories, Chinese translations, vocabulary tables |
| `CET4_Exercises.pdf` | 137 pages: one page of five exercises per chapter |
| `CET4_Answer_Key.pdf` | 20 pages: answers with explanations |
| `vocabulary_coverage.csv` | 6,127 rows — one per target, with its covering chapter and match evidence |
| `reports/manuscript.md` | the assembled bilingual manuscript, editable |
| `reports/qa_summary.json`, `reports/pdf_qa.json` | curriculum audit and per-page measurements |
| `quality_report.md` | the full measured QA report, including defects found and fixed |
| `vocabulary_coverage_report.md` | coverage accounting |
| `manifest.json` | machine-readable build manifest |

### Audio

`build/audio/` holds **one MP3 per chapter — 137 files, 6.43 hours, 144 MB** — each
one narrating that chapter's English story text, `CH001.mp3` through `CH137.mp3`.

| | |
|---|---|
| Voice | `Microsoft Zira Desktop` (en-US female), via offline Windows SAPI |
| Pace | rate `-2` → a measured median of **138 words per minute**, deliberately slower than narration |
| Format | MP3, mono, 22050 Hz, ~52 kb/s; 2.4–3.6 minutes per chapter |
| Tags | title `CHxxx · <title>`, album/artist `CET-4 Vocabulary Stories`, track `n/137` |
| Manifest | `build/audio/audio_manifest.json` — per chapter: words, duration, wpm, bytes, SHA-256, mid-slice level |

Every file was verified during generation, not assumed: present, duration consistent
with its word count at a plausible speaking rate (which is what catches truncated
synthesis), and a slice from the middle of the file above the silence threshold.
Measured across the set: 116 / 138 / 153 wpm minimum / median / maximum, and
−21.6 dB to −19.4 dB mid-slice level.

```bash
python build/make_audio.py                   # all 137 chapters, ~4 minutes
python build/make_audio.py --chapters CH001-CH005
python build/make_audio.py --voice "Microsoft David Desktop" --rate 0
python build/make_audio.py --verify-only
```

Two limitations, stated plainly:

- **English only.** This machine has no Chinese speech voice installed — every voice
  token in the registry is `en-US` — so the Chinese translations are not narrated.
  Installing one (Settings → Time & language → Speech → Manage voices → Add voices →
  中文(简体，中国)) is enough to extend the script to bilingual audio.
- **The voice is synthetic.** SAPI is offline and dependency-free, which is why it
  was chosen on a machine whose outbound network is unreliable; a neural voice
  (`edge-tts`, for example) would sound markedly more natural at the cost of a
  network round trip per file.

`build/make_audio.py` is Windows-only, like the PDF build: it needs `System.Speech`,
`ffmpeg` on `PATH`, and an installed voice. It runs the synthesis through a single
PowerShell process, because loading `System.Speech` per chapter would double the run
time.

All rendered PDFs were scanned for missing glyphs: **0 boxes across 420 files**
(3 root volumes, 414 preview volumes, 3 samples) covering 3,579,760 drawn
characters. All 420 rendered volumes are committed, including the 414 in
`build/preview/`, so the per-chapter PDFs are usable as a learning resource
without running the build.

---

## Repository layout

```
source/cet4_story/     the build system
  validation.py          the chapter validator: word counts, coverage, continuity
  batch.py               batch commit/checkpoint logic
  pdf_builder.py         A4 rendering for the three deliverables
  sample_builder.py      the sample-chapter renderer
  pdf_text.py            shared CJK font-run handling
  pdf_glyphs.py          definitive .notdef-box detection
  reporting.py           coverage CSV, manuscript, QA summary
  cli.py                 the `cet4-stories` command line
tests/                 94 tests, including the acceptance gates
drafts/batches/         the 137 chapters, 34 validated batch files (source of truth)
drafts/sample_chapters.json   the approved samples CH001/CH050/CH090
specs/                 the generation and validation specification
data/                  the confirmed vocabulary source, metadata, provenance, ECDICT license
build/                 QA tools, edit patches, validation certificates, rendered volumes, audio
build/val-*.json       one certificate per batch: the four gates and counted totals
build/preview/         414 rendered volumes: 3 combined previews + 137 x 3 per chapter
build/audio/           137 chapter MP3s + the per-chapter audio manifest
build/qa/              contact sheets for visual review, plus the detector's baseline
reports/               generated manuscript and QA output
LICENSE                MIT, for the software
LICENSE-CONTENT.md     CC BY 4.0, for the curriculum content
curriculum_plan.csv    the protected allocation of all 6,127 targets (hashed)
review_schedule.csv    the protected spaced-review schedule (hashed)
vocabulary_master.csv  the protected enriched vocabulary master (hashed)
```

### Evidence kept in `build/`

Nothing under `build/` is a throwaway. The rendered volumes are committed so the
material is usable as a learning resource without building anything:
`build/preview/` holds the three combined preview volumes (501 + 137 + 20 pages)
and 137 x 3 per-chapter volumes, and `build/CET4_Sample_*.pdf` holds the three
approved samples. `build/qa/` holds the contact sheets used for visual review.

`build/val-*.json` holds one certificate per batch recording whether it passed all
four gates (schema, plan, coverage, continuity) and its counted totals, so a reviewer
can confirm every batch was validated against the content actually shipped without
running anything. The 34 certificates total 5,992 verified new targets and 2,412
verified review occurrences; the remaining 135 + 36 belong to the three approved
sample chapters.

They were previously produced by hand, which made them orphans: nothing regenerated
them, and after the text was revised they still certified the older version. They are
now produced by `build/refresh_validations.py`, which also fails if any has gone
stale:

```bash
python build/refresh_validations.py           # rewrite every certificate
python build/refresh_validations.py --check    # fail if any is missing or stale
```

`build/qa/stories-baseline.pdf` is kept as well, and it is the one file here that is
**deliberately defective**: it is the pre-fix build (8,452 boxes), retained as the
negative control for `build/notdef_scan.py`. A detector that reports zero on a broken
file proves nothing, so this file is what makes the "0 boxes" claim checkable.

Authoritative progress lives in `drafts/batches/checkpoint.json`. Read it with
`build/checkpoint_state.py`; do **not** read `rebuilt_from_disk` from
`checkpoint-status`, which counts unvalidated batch files on disk and can overstate
progress.

---

## Reproducing and verifying

Requires Python 3.12 and, for PDF rendering, a Windows font set: the builders read
`C:\WINDOWS\Fonts\arial.ttf`, `arialbd.ttf`, and `simhei.ttf` directly. This is a
Windows-only build dependency (a documented limitation, not an oversight).

```bash
uv sync

# validate every chapter, write the coverage CSV and the manuscript
uv run cet4-stories --project-root . audit-curriculum

# protected sources and invariants: 6,127 records, 137 chapters, 36,762 review events
uv run cet4-stories --project-root . verify-sources

# rebuild the three deliverable PDFs
uv run cet4-stories --project-root . build-pdfs --selector all \
    --out . --prefix CET4_Vocabulary --no-per-chapter

# gates
uv run pytest -q
uv run ruff check source tests build
uv run python build/notdef_scan.py     # 0 boxes required
uv run python build/glyph_qa.py        # font coverage of every drawn character
uv run python build/final_qa.py        # A4, blank pages, boundaries, embedded fonts
uv run python build/spill_check.py     # short/spill pages
```

`build/notdef_scan.py` is the check to trust for missing glyphs. It counts glyph id
0 (`.notdef`) in the PDF text trace. Counting U+FFFD in extracted text does **not**
work: the PDF stores the correct character and only the glyph is missing, so
extraction looks clean while the page prints a box.

---

## How this was built, and what went wrong

The generation was automated in batches of at most 8 chapters, with a checkpoint
written only after four validators pass: schema, plan conformance, whole-word
coverage, and cross-chapter continuity.

The report at [`quality_report.md`](quality_report.md) records the defects that
reached a "passing" QA run and how each was found, because they share one cause —
**a proxy was verified instead of the property**:

| Defect | Scale | Why the checks missed it |
|---|---|---|
| IPA printed as boxes | 4,540 rows | SimHei lacks 15 of 19 IPA characters; the QA counted U+FFFD, which this defect never produces |
| Chinese heading and quoted meanings printed as boxes | 1,292 more | reportlab does not fall back between fonts; a source-side cmap check assumed Latin text is always drawn with a Latin font |
| Sample volumes printed as boxes | 168 more | `build-sample-pdfs` uses a second renderer that had its own copies of the same bugs; only found by scanning all 417 rendered PDFs |
| Chinese was abridged, not translated | 113 paragraphs | every chapter had equal paragraph *counts*; the property itself was never measured |
| Review lists verified by substring | 1 chapter | a substring match was accepted as a whole-word match |

Each fix carries a guard: a deterministic glyph check with tests, a calibrated
translation-density gate, and a regression test for the matcher.

---

## Limitations

**Human semantic review has not been performed and is not claimed.** 6,127 targets
are placed and machine-verified, but no human has judged whether every placement
reads naturally or is pedagogically useful. Specifically outstanding:

- 41 targets have no part of speech from any available source
- 48 targets have no phonetic transcription
- every protected vocabulary row is marked `needs_review=yes` as a global marker,
  not as per-item triage

**Known deviations**, all recorded with measurements in `quality_report.md`:

- **Vocabulary-table spill pages**: 9 pages of the 501-page volume hold a single
  table row. A fix was attempted (501 → 473 pages) and reverted on evidence, because
  it raised the count of sparse pages from 9 to 16.
- **English naturalness**: some sentences were built to host a mandated word and
  read stiffly, e.g. `they produced an argumentation they could both sign`. This is
  accepted as-is and documented rather than hidden.
- **CH042 contains mild profanity.** The word is a *mandated CET-4 target* for that
  chapter in the protected plan; removing it broke coverage (179/180 targets
  verified). It is left in place and flagged here. Changing it means editing the
  protected curriculum plan or presenting that target differently.
- **No physical print test** was performed. All PDF validation is programmatic plus
  sampled visual inspection of rendered contact sheets.

---

## Data provenance and licensing

The vocabulary source, its provenance, and the protected-source hashes are
documented in `data/source_provenance.md` and `data/cet4_metadata_manifest.json`.
The project never labels an unconfirmed online list as official.

**Third-party data.** `data/cet4_metadata_subset.jsonl` and the ECDICT-derived
metadata are redistributed under the **MIT License, Copyright (c) 2022 SmartCoding**
— the full text is included at `data/LICENSE.endict.txt`.

**This project's licensing.** Two licenses, because the repository holds two kinds
of work:

| Scope | License |
|---|---|
| Software — `source/`, `tests/`, `build/`, `pyproject.toml`, `uv.lock`, `specs/` | **MIT** (`LICENSE`) |
| Content — the chapters, translations, exercises, answer key, manuscript, rendered PDFs, and the explanatory documents | **CC BY 4.0** (`LICENSE-CONTENT.md`) |

CC BY 4.0 allows sharing and adaptation, including commercially, provided the
attribution requirement is met. If you would rather keep all rights reserved, or
use a different license, replace those two files — nothing else in the repository
depends on them.
