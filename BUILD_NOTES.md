# Build notes: how this curriculum was made, and what went wrong

This is the engineering log for the project. It records the pipeline, the defects that
reached a *passing* QA run, how each was found, and the guard that now prevents it. It
exists because the failures were more instructive than the successes, and because most
of them shared a single cause.

`quality_report.md` holds the measurements. This file holds the reasoning.

---

## 1. The pipeline

```
vocabulary source  ->  import/normalise  ->  allocation plan (protected, hashed)
                                              |
                          spaced-review schedule (protected, hashed)
                                              |
              chapter generation in batches of <= 8  ->  four validators  ->  checkpoint
                                              |
                    +-------------------------+-------------------------+
                    |                         |                         |
              A4 PDF volumes            chapter MP3s            chapter MP4s
              (story/exercise/answer)   (SAPI narration)        (burned-in subtitles)
```

The four validators are the gate. A batch is committed only if all of them pass:

| Gate | What it establishes |
|---|---|
| schema | the batch document matches the expected shape |
| plan | every planned target for those chapters appears, and no unplanned ones |
| coverage | each target is present as a **whole word**, not a substring |
| continuity | the chapter-to-chapter state carries over correctly |

The checkpoint is authoritative. `build/checkpoint_state.py` reads it; the
`rebuilt_from_disk` block printed by `checkpoint-status` counts unvalidated batch files
on disk and can overstate progress, which is why it is not the number to quote.

Determinism is what makes the rest verifiable. SAPI synthesis reproduces the committed
MP3s byte-for-byte for the same voice, rate and SSML, and the MP3 encoder is
deterministic too — both were checked, not assumed. That is what allows the audio to be
trusted as the timing reference for the subtitles without touching it.

---

## 2. The recurring failure: checking a proxy instead of the property

Every defect below passed an automated check that was measuring something adjacent to
what actually mattered.

| # | The property that mattered | The proxy that was checked | What got through |
|---|---|---|---|
| 1 | the font has a glyph for every character drawn | extracted text contains no U+FFFD | 4,540 phonetic rows printed as boxes |
| 2 | the paragraph's *style* draws text its font can render | "Latin text uses Arial, everything else uses SimHei" | 1,292 more boxes |
| 3 | every renderer produces clean output | the three deliverable PDFs produce clean output | 168 boxes in a second renderer |
| 4 | the English is actually rendered in Chinese | the paragraph **counts** match | 113 paragraphs were summaries, not translations |
| 5 | a planned target appears as a word | a substring of the text matches | one chapter verified by substring |
| 6 | the validation certificate describes the shipped text | a certificate exists | all 34 were stale |
| 7 | subtitle times match the audio | the word events were interpreted with the right offsets | every sentence after an apostrophe was mis-assigned |
| 8 | the event clock is real time | last event time vs audio length | a 37% scale error nobody noticed |
| 9 | the offsets were right | a median bias correction made the mean error zero | spread stayed at 0.24 s, so drift remained visible |

### 1–3. Glyph boxes (5,832 of them, in three places)

`build/notdef_scan.py` now counts glyph id 0 in the PDF text trace, which is the
definitive signal: a box *is* a `.notdef` substitution.

Two detectors were tried and discarded first. Counting U+FFFD in extracted text cannot
see this class at all — the PDF stores the correct character and only the glyph is
missing, so extraction returns clean text while the page prints a box. A source-side
cmap check caught the phonetic column but **assumed Latin text is always drawn with a
Latin font**; it passed the other two sources because Chinese was being drawn in an
Arial-styled paragraph.

The third source was only found by scanning all 417 rendered PDFs instead of the three
deliverables: `build-sample-pdfs` uses a near-duplicate renderer that had its own copies
of all three bugs. **A duplicate renderer is exactly where a fixed bug survives.**

The working detector was validated against a known-bad file (8,452 boxes) before being
trusted, because a detector that reports zero on a broken file proves nothing.

### 4. Translation that was not translation

The spec requires one Chinese paragraph per English paragraph, and every chapter had
equal counts — so every gate passed. The abridgement was invisible because no check ever
compared the *content*. Measured by density (CJK characters per English word) against
this corpus's own distribution (median 1.48), **113 of 738 paragraphs** fell below 1.2
and were rewritten. The gate is now density, and it is calibrated from the corpus rather
than chosen.

The sentence-gap metric was tried and rejected as a gate: it cannot distinguish a dropped
sentence from a legitimate merge, and it produced both false positives (quoted speech) and
a false negative (a dense paragraph whose final clause had been dropped).

### 5. Substring coverage

`cross` was satisfied by a word containing it as a substring. Coverage now requires a
whole-word match, and a regression test pins it.

### 6. Certificates nobody regenerated

`build/val-*.json` had been produced by hand, by redirecting `validate-batch` output. When
the text was later revised the certificates still certified the old version — all 34 were
stale. Shipping them would have published evidence that did not describe the repository.
`build/refresh_validations.py` now generates them and **fails if any has gone stale**, which
a hand-maintained evidence file cannot do.

### 7–9. Subtitle synchronisation

The hardest one, and the clearest example of the pattern.

**Cause 1 — character offsets were shifted.** Word events index the **SSML string**, so
paragraph offsets were taken from the SSML. But `html.escape` escapes apostrophes to
`&#x27;`, and SAPI counts that entity as **one** character rather than six. Every word
after an apostrophe was therefore reported at an offset five characters early, which
mis-assigned words to sentences. The corpus has 60 apostrophes, so nearly every chapter
was affected.

The fix is `html.escape(text, quote=False)`: only `&`, `<` and `>` need escaping inside
element content, and this corpus contains none of them, so offsets are now 1:1. **The
committed audio is unchanged** — the regenerated MP3 is byte-identical and its decoded PCM
matches, which was verified rather than assumed.

**Cause 2 — the clock was misread.** `AudioPosition` is not real time. The first reading
divided the last event time by the audio length and concluded a 1.366× inflation; that was
wrong, because the last event is the **start** of the final word, not the end of the audio.
Fitting the paragraph anchors instead gives

```
audio_time = 0.7256 * event_time + ~0.01        maximum residual 4-10 ms
```

across every chapter sampled. `0.725625` is `16000/22050`: SAPI reports against a 16 kHz
stream while the audio is written at 22.05 kHz. The scale is **fitted per chapter**, not
hard-coded, so a format change would surface as a residual instead of silently skewing
every line.

**Cause 3 — a fix that treated the symptom.** Before cause 1 was understood, a bias
correction was added that measured the median error against nearby pauses and shifted the
cues by it. It brought the mean error to zero and left the spread at 0.24–0.30 s — which is
precisely what "the words and the voice drift apart" looks like. Removing it after fixing
the real cause dropped the spread to **0.006 s**. The lesson is not "do not correct bias";
it is that a residual bias with a large spread means the model is wrong, not merely offset.

### Verifying the result independently

`build/check_sync.py` compares the finished `.srt` files against **the audio alone** — cue
starts against speech onsets detected in the recording. That is a different measurement
from the events that produced the cues, so it can catch a systematic error the tool's own
gates cannot.

Two false alarms had to be worked through before the check was trustworthy, and both were
failures of the *measurement*, not the artefact:

1. **The first cue of every chapter looked wrong.** Its start is clamped to zero because
   there is no room for a lead-in at the very beginning, so "cue start + lead" points
   somewhere the sentence never was. Excluding it removed an invented outlier from all 137
   chapters.
2. **Sentences that begin inside quoted dialogue looked wrong.** In
   `"...small habits," the coach said, "and you are optimistic..."` the splitter starts a
   cue after a comma pause that is too short for the silence detector, so that onset is
   missing from the reference set and the offset reads 2–3 s. Checking the audio settled
   it: the level at the expected time was **-17.6 dB**, i.e. speech, so the cue was right.
   The drift gate therefore uses the **interquartile range** instead of the standard
   deviation; one such cue would drag a stdev past any useful threshold while the timing
   is correct.

The check also verifies the lead-in transitively. It measures
`(cue start + lead) - nearest onset` and requires it near zero: had the lead not been
applied, the cue start would already be the onset and every value would read about `+lead`.

Full-run result over all 137 chapters:

| Measure | Value |
|---|---|
| cues compared | 2,707 |
| median offset | **+0.000 s** |
| median interquartile spread | **0.013 s** (0.24–0.30 s before the offset fix) |
| cues beyond 0.35 s | 3 (0.11%), all confirmed to be undetected comma onsets |
| cues whose expected speech time is silent | **0** |
| clock scale fitted per chapter | 0.725397–0.725800 |
| worst clock-fit residual | 17.7 ms |

### The typing game: what a test caught that reading the code did not

`CET4_Typing_Game.html` is generated from `game/template.html` by
`build/make_typing_game.py`, and it is verified three ways: pytest against the vocabulary
data, a Node smoke test that drives the game logic out of the generated page, and headless
screenshots for the rendering.

The pytest test asserted that every embedded word is *typeable* — that nothing in the list
needs a keystroke the page cannot produce. It failed on the first run:

```
AssertionError: cell phone is untypeable
```

**14 entries are phrases** — `ice cream`, `according to`, `living room`, `middle class` —
and the keystroke filter accepted letters, apostrophes and hyphens but not spaces. Every
one of those words would have fallen to the floor, cost a life, and been impossible to
clear, in every round. The fix is that a space types when it is the next character of the
word being typed, and pauses otherwise.

This is the same failure mode as everything in section 2 — a property nobody checked — with
one difference: here the check existed *before* the defect reached anyone. Writing the
assertion is what found it, which is the argument for testing data-driven UI against its
source rather than only looking at it.

Two traps came up again while verifying the rendering, and both produce a screenshot that
looks like a broken page:

| Trap | What it looked like | Reality |
|---|---|---|
| `Get-Content -Raw \| Set-Content -Encoding UTF8` on a probe file | every Chinese label rendered as mojibake (`ç†åˆ†` for `得分`) | the probe was double-encoded; the page was fine, proved by a copy made with `Copy-Item` |
| headless `--virtual-time-budget` | an empty board, no falling words | `requestAnimationFrame` ran **twice** in the whole window, so the spawn timer never fired. The probe now stages the state it wants drawn and calls the same `draw()` the game uses |

Both are the lesson from section 3, which is why it is written down twice: a verification
harness is code, and it deserves the same scepticism as the thing it verifies. When a
screenshot looks wrong, the first question is which part of the chain produced it.

#### Choosing what counts as a key word

The game can drill a chapter's hardest words instead of all 45, and the definition of
"hardest" was measured rather than assumed. The attractive answer was already in the data:
the ECDICT metadata carries **Collins star ratings** (89.3% filled) and an **Oxford 3000
flag** (47.8%), which look like exactly the importance signal a study tool wants.

Measured against the corpus, both are wrong here:

| Signal | Flags | Misses |
|---|---|---|
| Oxford 3000 or Collins ≥ 4 | 1,051 words of five letters or fewer: `I`, `a`, `about`, `yes`, `three` | 1,105 words of nine letters or more, including `accommodate`, `absorption`, `characterize` |

Two reasons. First, for a **typing** game the axis is spelling load, not frequency —
drilling `yes` is worth nothing and `accommodate` is the whole point. Second, word
frequency is redundant here at all: the CET-4 syllabus has already selected these 6,127
words, so every one of them is a legitimate target and the only open question is which
need the most practice. The rule that follows is:

```
重点词  =  len >= 9  or  (len >= 7 and (Oxford 3000 or Collins >= 4))
```

Measured: 2,439 words (39.8%), 17.8 per chapter, minimum 5. It admits **no word shorter
than seven letters** and misses no long word. Chapters whose key set falls below six words
are topped up from the chapter's longest remaining words, so a drill is never empty.

The generalisable part is not the formula. It is that the data's own notion of importance
answered a different question from the one being asked, and only measuring it showed that.
The same test — does this signal rank what *this* tool needs ranked? — is what caught the
proxy defects in section 2.

#### The Chinese under each word is a sense, not the entry

Showing the Chinese under every falling word turns the board into a flashcard, which is
what it was asked for. The obvious implementation — draw `chinese_meaning` — is wrong: that
field is a dictionary entry, and the longest are things like
``n. 原料, 要素, 东西, 材料, 素质, 织品, 废物, 废话``. Three lines of that stacked under
each of up to eight falling words is not readable at the speed the words fall.

So the generator emits a second, shorter gloss for this line: keep the part of speech and
the **first sense**, cap it at 14 characters. ``n. 原料`` instead of the whole entry. The
full gloss is not lost — it is what the hint bar shows for the word actually being typed.

Because that field is derived rather than copied, it is the kind of thing that can silently
drift into nonsense, so the test checks it as a claim: every short gloss must be non-empty,
at most 15 characters, free of list separators, and its sense must actually appear in the
real gloss. All 6,127 pass, and only 10 needed truncating.

---

## 3. Environment traps

Each of these cost real time and is specific enough to be worth writing down.

| Trap | Symptom | Handling |
|---|---|---|
| PowerShell 5.1 `Get-Content -Raw \| Set-Content -Encoding UTF8` | silently double-encodes non-ASCII in a BOM-less UTF-8 source file → mojibake in a rendered card | never rewrite source that way; use the editor |
| PowerShell has no heredoc; here-strings mangle f-strings | `SyntaxError: '{' was never closed` | write a temp `.ps1`/`.py` file and run that |
| ffmpeg's filter parser treats `:` as an option separator | `subtitles=D:/...` → "Unable to parse original_size" | run ffmpeg with `cwd` = the subtitle's directory and pass the bare filename |
| `pwsh` (PowerShell 7) not installed; only 5.1 | `FileNotFoundError: pwsh` | resolve `pwsh` or `powershell` at runtime |
| Execution policy blocks generated scripts | "running scripts is disabled on this system" | `-ExecutionPolicy Bypass` for that process only |
| PowerShell 5.1 rejects a trailing comma in an array literal | parser error in generated script | emit one statement per item |
| ID3 metadata is part of the file | two MP3s differ byte-wise while sounding identical | compare **decoded PCM**, not container bytes |
| A player holds the output file open | ffmpeg "Permission denied", the whole run dies | write to a temp file, swap it in, skip and report if locked |
| A player auto-loads `CH001.srt` beside `CH001.mp4` | every subtitle appears twice, in two styles | keep sidecars in a `subtitles/` subdirectory |
| `-shortest` against a looped still image | output ran ~3 s past the audio | cap with `-t <duration>` |
| `api.github.com` reachable while `github.com:443` is not | `git push` fails; `ls-remote` times out | publish through the Git Data API on the reachable host |
| A GitHub repo rejects blob creation while completely empty | HTTP 409 "Git Repository is empty" | initialise with one file, then force the branch to the real commit |
| GitHub's license detector | reports `NOASSERTION` despite an MIT `LICENSE` | keep `LICENSE` as pure MIT text; put scope notes elsewhere |
| headless `--virtual-time-budget` | an empty canvas that looks like a render bug | `requestAnimationFrame` barely runs under virtual time; stage state and call the draw function directly |

Two of these were self-inflicted and worth naming: the mojibake came from rewriting a
source file with PowerShell, and the doubled subtitles came from putting a sidecar where
players look for it.

---

## 4. What this project does not claim

- **Human semantic review has not been performed.** 41 targets lack a part of speech, 48
  lack phonetics, and no human has judged whether the placements read naturally or are
  pedagogically useful.
- **The typing game has not been played.** Its data, logic and rendering are verified —
  7 pytest checks, 30 Node logic checks, and four headless screenshots — but nobody has
  actually played a round. The difficulty curve (a level every 10 words, up to 8 words on
  screen at once) is a reasonable guess, not a tuned value, and the spawn rate in
  particular may want adjusting after the first real session.
- **No physical print test** was performed. PDF validation is programmatic plus sampled
  visual inspection.
- 9 pages of the story volume carry a single vocabulary-table row. A fix was attempted
  (501 → 473 pages) and **reverted on evidence**, because it raised the count of sparse
  pages from 9 to 16.
- The narration is **English only**; no Chinese speech voice is installed on the build
  machine.
- Some English sentences were built to host a mandated word and read stiffly. This is
  documented rather than hidden.
- CH042's mandated target happens to be mild profanity. Removing it broke coverage
  (179/180 targets verified), so it is left in place.

---

## 5. Reproducing

```bash
uv sync                                   # dev + PDF dependencies
uv sync --extra audio                     # only if regenerating narration via edge-tts

uv run cet4-stories --project-root . audit-curriculum     # validate 137 chapters, write CSV + manuscript
uv run cet4-stories --project-root . verify-sources       # protected hashes and invariants
uv run cet4-stories --project-root . build-pdfs --selector all --out . \
    --prefix CET4_Vocabulary --no-per-chapter             # the three deliverable PDFs

python build/refresh_validations.py --check   # validation certificates match the batches
python build/font_registry_check.py 2>/dev/null || python build/glyph_qa.py   # fonts cover what they draw
python build/notdef_scan.py                   # 0 boxes required; the gate that actually sees them
python build/final_qa.py                      # A4, blank pages, boundaries, embedded fonts
python build/spill_check.py                   # short pages, with a contact sheet

python build/make_audio.py                    # 137 chapter MP3s (~8 min)
python build/make_video.py                    # 137 subtitled MP4s (~1 h)
python build/check_sync.py                    # subtitle timing, measured against the audio

python build/make_typing_game.py              # regenerate the game page from the vocabulary
node build/typing_game_smoke.mjs              # 30 checks on the game logic
python build/game_screenshots.py              # render the game's UI states headlessly

uv run pytest -q
uv run ruff check source tests build
```

The PDF and audio builds are Windows-only: the renderers read `C:\WINDOWS\Fonts\arial.ttf`,
`arialbd.ttf` and `simhei.ttf`, and the `sapi` narration path needs `System.Speech`. The
`edge` narration path needs a network round trip per chapter.

---

## 6. The one habit that mattered

Every defect above was caught by measuring the thing itself and comparing against an
independent reference:

- glyphs: compare against the font's own cmap, and confirm the detector fires on a known-bad file
- translation: measure density against the corpus's own distribution
- coverage: match whole words
- subtitles: measure the finished subtitles against the audio, not against the data that produced them
- content: compare tree SHAs, which is cryptographic rather than indicative

Where a check was trusted without an independent reference, it passed while the artefact
was broken.
