# Quality Report

All figures below were measured in this project, not estimated. Machine-readable
evidence: `reports/qa_summary.json`, `reports/pdf_qa.json`,
`reports/source_provenance.json`, `drafts/batches/checkpoint.json`.

## Environment and code

- CPython 3.12.14 through `uv` (`.venv`): PASS
- Locked dependency environment (`uv.lock`): PASS
- Ruff (`ruff check source tests --no-cache`): PASS
- pytest: PASS (**88 passed, 0 failed**)
- Chinese-capable fonts available and used (SimHei): PASS

## Vocabulary source and metadata

- Target source SHA-256: verified in `reports/source_provenance.json`
- Unique target IDs/lemmas: 6,127 / 6,127
- Exact ECDICT metadata matches: 6,127 / 6,127
- Chinese meanings: 6,127
- Phonetics: 6,079; missing 48
- Part of speech: 6,086 from the protected CSV; 41 unresolved
- Fuzzy or substring matches counted as coverage: 0

## Curriculum

- Planned chapters: 137
- Generated chapters: 137 (CH002–CH137 in 34 batches; CH001/CH050/CH090 preserved)
- Chapter IDs: 137 unique, consecutive CH001..CH137
- Chapters with 45 new targets: 99; with 44: 38; total 6,127, no duplicates
- Review rows in `review_schedule.csv`: 36,762
- Contextual story-review assignments: 2,448 (all verified)

  The persisted checkpoint reports `verified_new: 5,992` and
  `verified_review: 2,412` because it counts only the 134 generated batches; the
  audit adds the 3 preserved sample chapters (CH001/CH050/CH090) on disk and
  reaches 6,127 new and 2,448 review occurrences. Both numbers are correct for
  what they measure; neither is an estimate.
- Exercise/answer ID pairs: 685 (5 per chapter, ids `CHxxx-Q1`..`CHxxx-Q5`)

## Per-chapter structural checks (all 137 chapters)

- English word count within 350–450: PASS
- Paragraph count within 4–6 with equal English/Chinese counts: PASS
- No empty English or Chinese paragraph: PASS
- Exactly 5 exercises and 5 answers with matching IDs: PASS
- Exercise prompt never contains its own answer: PASS
- Every mandated new lemma and review lemma present as a whole word in the
  English story: PASS

The last two rules rejected real defects during generation and were not waived:
one exercise prompt leaked its answer (`CH069-Q4`), one leaked the word
`nothing` (`CH094-Q4`), and repeated misses came from apostrophe (`nap's`),
hyphen (`seventy-year-old`), spelling-variant (`centimetre` vs. `centimeter`,
`favourable` vs. `favorable`, `aluminium` vs. `aluminum`, `woollen` vs.
`woolen`), and inflection (`statistics` vs. `statistic`) mismatches against the
protected entry forms.

## Final PDF checks

| Volume | Pages | Bytes | A4 | Blank | U+FFFD | Boundary violations | Min extracted chars |
|---|---|---|---|---|---|---|---|
| `CET4_Vocabulary_Stories.pdf` | 501 | 3,066,438 | yes | 0 | 0 | 0 | 279 |
| `CET4_Exercises.pdf` | 137 | 277,409 | yes | 0 | 0 | 0 | 602 |
| `CET4_Answer_Key.pdf` | 20 | 139,659 | yes | 0 | 0 | 0 | 173 |

Byte sizes vary between rebuilds because PDFs embed creation metadata; page
counts and measurements are stable across rebuilds of the same source.

- A4 portrait on every page of every volume: PASS
- Blank pages: 0
- Chinese replacement glyphs (U+FFFD and tofu markers): 0
- **Boxes (`.notdef`, glyph id 0): 0 in all three volumes: PASS**
  (`build/notdef_scan.py`, `tests/test_pdf_glyphs.py`). This is the gate to trust;
  the U+FFFD count above is structurally incapable of seeing boxes - see the defect
  section below.
- Source-side font coverage (`build/glyph_qa.py`, `tests/test_glyph_coverage.py`):
  PASS. It catches a font that cannot draw a string you already know about; it
  cannot catch a string drawn with the wrong style, which is how 1,292 boxes got
  through it.
- Text blocks exceeding the page box on any page: 0
- Fonts: Arial, Arial-Bold, and SimHei embedded TrueType subsets. The exercise
  volume now uses 5 font resources (4 embedded) rather than 4 (3), because
  prompts correctly mix Arial for the English with SimHei for a quoted Chinese
  meaning on the same line.
- Every font that actually paints a glyph is embedded: PASS
  (`/Helvetica` is declared in the page resources because reportlab emits an
  empty `BT /F1 12 Tf … ET` block at the start of each page; it paints no glyph,
  which was verified by parsing the content stream rather than assumed)
- Rendered-page inspection: sampled contact sheets at the beginning, middle,
  end, and table-heavy pages of each volume
  (`build/qa/contact-CET4_*.png`), plus a before/after pixel comparison of the
  glyph fix (`build/qa/glyph-fix-page2.png`); no overlap, clipping, or boxes seen
- **Physical printer test: NOT PERFORMED**

## Defect: .notdef boxes, in three separate places

The first QA run reported `tofu=0` and was wrong, twice over. Counting the U+FFFD
replacement character in extracted text cannot see this defect at all: the PDF
stores the correct character and only the glyph is missing, so extraction returns
clean text while the page prints a box. A user found the boxes, and two rounds of
"fixes" were needed, because the first round only removed the source that had been
photographed.

| Source | Boxes | Why |
|---|---|---|
| Phonetic column, drawn with SimHei | 4,540 rows | SimHei cannot draw 15 of the 19 non-ASCII phonetics characters (`æ ð ŋ ɒ ɔ ə ɜ ɪ ʃ ʌ ʒ ˈ ˌ є ә`); Arial covers all 19 |
| `中文翻译` heading, `styles["section"]` | 548 (137 chapters x 4 characters) | reportlab does not fall back between fonts, so Chinese inside an Arial-Bold paragraph draws boxes |
| Chinese meanings quoted inside exercise prompts, `styles["question"]` | 744 | same cause, inside an Arial paragraph |
| `CET4_Answer_Key.pdf` | 0 | it already drew Chinese with the CJK style |

Fix: the lemma and phonetic runs are tagged `<font name="CETEnglish">` (Arial), and
`cet4_story.pdf_builder.with_cjk_font()` wraps CJK runs in
`<font name="CETChinese">` for any paragraph styled with a Latin font. All three
volumes now report **0 boxes** (`build/notdef_scan.py`).

### A second renderer had its own copies of all three defects

`build-sample-pdfs` does not use `pdf_builder`; it has a near-duplicate renderer in
`sample_builder.py`. When all 417 rendered PDFs were scanned rather than just the
three root volumes, the sample volumes still contained **168 boxes** - 145 from IPA
drawn with SimHei, 12 from the same Chinese heading, 11 from the same exercise
prompt. The first round of fixes could not have found them, because only the root
files were checked. `sample_builder.py` now imports the shared helper and tags its
IPA runs the same way.

Two lessons worth keeping:

- Scan **every** rendered artifact, not the one you were handed. A duplicate
  renderer is exactly where a fixed bug survives.
- The fix belongs in a shared module. Importing the helper from `pdf_builder` into
  `sample_builder` created a circular import (`pdf_builder` already imports
  `sample_builder`), and `build-sample-pdfs` then failed while producing no output -
  a silent no-op that only the scan caught. The helper now lives in
  `cet4_story/pdf_text.py`, which neither builder imports from the other.

### Current state of every rendered PDF

| Set | Files | Verified |
|---|---|---|
| Root deliverables | 3 | 0 boxes |
| `build/preview/` combined + per chapter | 414 | 0 boxes |
| `build/CET4_Sample_*.pdf` | 3 | 0 boxes |
| **Total** | **420** | **0 boxes across 3,579,760 drawn characters** |

`build/qa/stories-baseline.pdf` is deliberately excluded: it is the pre-fix file
kept to validate the detector, and it contains 8,452 boxes on purpose.

A fourth instance of the same class was caught by the source-side check: **CH088's
Chinese paragraph 2 contained two U+200B zero-width spaces**, which are invisible in
most editors but print as boxes. They were removed; the batch re-validated with
byte-identical counts, and only that batch's hash was refreshed, because
`commit_batch` has no idempotence guard and re-committing would double-count.

### The detector itself had to be replaced, twice

- Counting U+FFFD: missed every box.
- Source-side font-cmap check (`build/glyph_qa.py`): caught the phonetic column, but
  only because it modelled "Latin text -> Arial, everything else -> SimHei". That
  model was wrong about **which style draws which text**, so it passed the other two
  sources.
- Per-span font lookup from the PDF: does **not** work here. The CID subsets have
  unreliable ToUnicode entries, so `page.get_text("rawdict")` returns `\x00` or a
  guessed character. That attempt produced 203,870 false positives including `的`,
  `—` and `“`, all of which render correctly. It was discarded rather than shipped.

The check that works is definitive: a box means the renderer substituted glyph id 0
(`.notdef`), and PyMuPDF's text trace exposes the glyph id of every character
actually drawn. `cet4_story.pdf_glyphs.scan_notdef` counts `gid == 0` per page and
font; `build/notdef_scan.py` exits non-zero on any box; `tests/test_pdf_glyphs.py`
gates the three deliverables on it. It was validated against a known-bad file first
(it found 8,452 boxes there), because a detector that reports zero on a broken file
proves nothing.


## Data observation for human review: Cyrillic look-alike IPA

The phonetics come from ECDICT and use Cyrillic look-alikes for two sounds:
`ә` (U+04D9, Cyrillic small schwa) appears in **4,167** rows where IPA `ə`
(U+0259) would be expected, and `є` (U+0454) appears in 88 rows. They are visually
almost identical to the IPA characters, and Arial now draws them correctly, so the
printed page is readable. They are nonetheless not standard IPA.

The protected source was **not** modified: the spec forbids silently changing the
target data. Normalising them at render time is a one-line change if you want
strict IPA on the page.

## Chinese translation completed (was a documented open defect)

The spec requires "one accurate Chinese paragraph per English paragraph". After
generation, 113 of 738 paragraphs were abridged *summaries* rather than
translations, because English sentences were appended to reach the 350-word floor
and never rendered in Chinese. Paragraph counts were aligned, so every gate passed;
the property itself had never been checked.

Measured by density (CJK characters per English word), against this corpus's own
distribution - a faithful rendering runs at a median of 1.48 and a 25th percentile
of 1.36:

| | Before | After |
|---|---|---|
| Paragraphs below 1.2 (summaries) | **113** | **0** |
| Residual sentence-count gaps | (not measured) | 10 |

All 113 paragraphs were rewritten. The residual 10 sentence-count gaps were each
inspected by eye and are **merges**, not omissions: Chinese legitimately renders
"Some looked helpless." as a clause of the preceding sentence, and a quotation plus
its reporting clause as one sentence. The metric cannot tell a merge from a drop,
so it is reported but not gated; `test_every_paragraph_is_rendered_in_chinese`
gates on density and bounds the residual count so a real regression still fails.

## Arc carry-over sentences added (19)

Each arc opener now begins with an in-world sentence referencing the previous arc's
outcome, and each arc closer ends with an echo of its theme, so the 137 chapters
read as one continuous line rather than ten unrelated sequences:

- openers: CH015, CH029, CH043, CH057, CH071, CH085, CH099, CH113, CH127
- closers: CH014, CH028, CH042, CH056, CH070, CH084, CH098, CH112, CH126, CH137

CH001 is the first chapter and needs no recap. CH137 has no successor bridge
chapter, so its closing line states that fact rather than pretending otherwise.
Every addition carries its Chinese counterpart, and each chapter stayed within
350-450 words.

## Known cosmetic deviation: vocabulary-table spill pages

Nine of the 501 story pages (1.8%) carry only the final row of a chapter's
vocabulary table - the table's last row spills onto a fresh page. Measured with
`build/spill_check.py`, which parses the PDFs directly:

| Page | Extracted characters |
|---|---|
| 51 | 315 |
| 185 | 297 |
| 244 | 279 |
| 271 | 282 |
| 323 | 321 |
| 357 | 324 |
| 379 | 291 |
| 442 | 280 |
| 456 | 310 |

These pages are not blank, not clipped, and not defective: every table row and
every glyph is present and inside the page box. The rendered contact sheet
`build/qa/contact-sparse-CET4_Vocabulary_Stories.png` shows all nine for review,
and `build/qa/contact-sparse-CET4_Answer_Key.png` shows the one short page in the
answer volume (its final page, which is short by nature). Both are produced by
`build/spill_check.py`, so they track the current layout instead of an older build.
The spec asks to avoid sparse spill pages, so this is recorded as an unmet
cosmetic preference rather than passed over.

A fix was attempted and reverted on evidence. Tightening the vocabulary table
leading from 8.0 to 7.7 and its row padding from 0.7 mm to 0.5 mm reduced the
volume from 501 to 473 pages, but raised the number of sparse pages from 9 to 16
(1.8% to 3.4%): the tighter setting only moved the split boundary and created
orphans in more chapters. The change was reverted and the layout re-verified at
501 pages with 9 sparse pages. A real fix needs the table to keep at least two
rows together across a split, which is a layout change rather than a spacing
tweak.

## Fixes made during this work

0. **Glyph coverage - four defects, two rounds of fixes.** 6,000 `.notdef` boxes
   reached rendered files: 4,540 phonetic rows drawn with SimHei (which lacks 15 of
   19 IPA characters), 548 from the Chinese `中文翻译` heading drawn with Arial
   Bold, 744 from Chinese meanings quoted inside Arial-styled exercise prompts, and
   - found only when all 417 rendered PDFs were scanned instead of the three root
   volumes - 168 more that `sample_builder.py` had produced independently: 145 IPA
   drawn with SimHei, 12 from the same heading, 11 from the same prompt. The lemma
   and phonetic runs now use Arial, `with_cjk_font()` wraps CJK runs for
   Latin-styled paragraphs, and the helper is shared through `pdf_text.py`. The
   U+FFFD check could not see any of this, and the first replacement check was
   built on a wrong model of which style draws which text, so it passed 1,292 of
   the boxes. The gate is now `build/notdef_scan.py` (glyph id 0 via the text
   trace) plus `tests/test_pdf_glyphs.py`, which covers all six deliverable-scale
   volumes.
0b. **Chinese translation.** 113 abridged paragraphs were rewritten to full
   translations, and 19 arc carry-over sentences were added. Four tooling bugs
   surfaced while doing it: the patch applier reported "nothing written" while it
   had already written earlier batches (fixed to per-batch atomicity); it treated
   `chinese` and `append_chinese` as either/or, silently dropping the Chinese half
   of five arc-closing echoes; its word counter used `str.split()`, which counts
   standalone em-dashes as words and so rejected a chapter that passes validation
   (it now calls the validator's own `count_english_words`); and it did not re-check
   coverage, so an editorial edit removed the mandated target `shit` from CH042 and
   the mandated review word `I` from CH058 - it now re-validates every file it
   writes.
0c. **Editorial pass.** CH042's profanity is mandated vocabulary and was therefore
   restored; CH058's first-person slip was reworded into a quoted margin note so
   the mandated `I` survives; CH062's was rewritten. See the section above.
1. Fixed a matcher defect where any uncertain derived candidate demoted a
   genuine exact match to `needs_revision` (triggered by the word `the`);
   regression test added.
2. Fixed `parse_ecdict_exchange` raising on a malformed ECDICT segment with an
   empty value; structural errors are still raised.
3. Corrected CH090, whose 45/45 coverage was a substring false positive.
4. Corrected two exercise prompts that contained their own answers.
5. Changed `tests/test_workpack.py` from hard-coded batch-size assertions to the
   exact invariant `len(next) == min(8, remaining)`, which holds while chapters
   remain and once all 137 are committed.
6. Added `build/checkpoint_state.py` after an operator error: `checkpoint-status`
   prints both the authoritative persisted checkpoint and a `rebuilt_from_disk`
   diagnostic that counts unvalidated batch files, and the diagnostic was briefly
   mistaken for committed progress.
7. Made `build/spill_check.py` measure the PDFs directly. It previously read
   `reports/pdf_qa.json`, so after a rebuild it silently reported the previous
   layout's numbers; that staleness caused one wrong reading during this work.

## Integrity observations for reviewers

- `commit-batch` refuses any batch whose validation is not fully clean
  (`source/cet4_story/batch.py`), so the persisted checkpoint only ever advances
  past batches with zero coverage and continuity errors. It is authoritative.
- `cet4-stories checkpoint-status` prints `rebuilt_from_disk` next to the
  checkpoint. That block counts every batch file present on disk, **including
  batches that failed validation and were never committed**, so it can read
  higher than the real progress. Use `build/checkpoint_state.py`, which reads
  `drafts/batches/checkpoint.json` only.

## Editorial items, and one you may want to decide

- **CH042's profanity is mandated vocabulary and could not be removed.** `shit` is
  a required CET-4 *target* for CH042 in the protected plan; replacing it broke
  coverage (verified: 179/180 new targets). It was restored and translated
  faithfully. Removing it needs a human decision, because the alternatives are to
  edit the protected `curriculum_plan.csv` or to present that target differently.
- **Narrative person: fixed.** CH058 read `I must say that we are still far from the
  offer` in third-person narration, and CH062 read `I am thankful for the small
  ones`. Removing CH058's `I` broke coverage, because `I` is a mandated *review*
  word there; it is now quoted - `A note in the margin said: "I must say that we
  are still far from the offer."` - which keeps the word and reads naturally.
  CH062 became `"Be thankful for the small ones," Maya said.`
- **English naturalness**: you chose to accept the current English. Some sentences
  were built to host mandated vocabulary and read stiffly, e.g.
  `they produced an argumentation they could both sign`,
  `it dealt honestly with the dealing of the previous month`,
  `The commencement of a method.`

## Remaining work

- **Human semantic review**: 41 unresolved part-of-speech entries, 48 missing
  phonetics, and context-appropriateness judgement for all 6,127 lemma
  placements. Not performed, not claimed.
- Optional physical print test.
