# Vocabulary Data Audit

## Target vocabulary source

- Official basis: 《全国大学英语四、六级考试大纲（2016年修订版）》
- Machine-readable transcription: `ismartcoding/endict`, commit `522c17036976c34c994a1d367bd61a7d9fa495d9`
- Target source SHA-256: `50143a67069cd69c0ce1221a6f7bb554b992b3295322344907bf784afb5ff9c0`
- Raw target rows: 6,127
- Unique case-insensitive target forms: 6,127
- Exact duplicate rows: 0
- Blank lemmas: 0

The official combined CET-4/CET-6 list reports 5,418 grouped headword entries and marks CET-6 groups with `★`. The selected CET-4 transcription expands non-starred groups, derivatives, and parallel spellings into 6,127 independently tracked forms. This is intentionally larger than the approximate 4,500 word-family count and avoids silently merging same-root words.

## Metadata enrichment

- Metadata source: ECDICT `ecdict.csv`
- Metadata source SHA-256: `1a6947e04785db63613a92e14903cdae7954f7e84860b10e68e5c7cbb3f9c3cf`
- ECDICT rows scanned: 770,611
- Exact single-candidate matches: 6,127
- Ambiguous exact matches: 0
- Unmatched targets: 0
- Chinese translations present: 6,127
- Phonetics present: 6,079
- Source POS values present: 0
- POS extracted from explicit translation prefixes: 6,086
- POS unresolved: 41
- Matching method: case-insensitive exact whole-entry match; no substring or fuzzy match counted

ECDICT is an MIT-licensed third-party dictionary compilation. Its translations, phonetics, examples, frequencies, and inflections are not official CET annotations and remain reviewable metadata.

## POS handling

The current ECDICT CSV has blank `pos` values for all selected entries. A deterministic rule extracts explicit prefixes such as `n.`, `vt.`, `vi.`, `a.`, `adv.`, and `prep.` from the supplied translation. Extracted values are stored in both `part_of_speech` and `inferred_part_of_speech`; `pos_inference_method` records `translation_prefix`. The untouched `ecdict_pos` field remains blank, so inferred POS is never presented as source-provided POS.

### POS unresolved (41)

a, according to, affordable, agenda, air conditioner, air conditioning, am, app, bacteria, brand new, cyberspace, data, dating, download, durability, facilitation, founding, funding, goodbye, hacker, hello, hi, Homo, ice cream, imaging, Internet, laptop, living room, middle class, networking, online, ought to, owing to, privatization, quantification, scissors, second hand, standardization, trousers, upload, well off

### Missing phonetics (48)

according to, affordable, air conditioner, air conditioning, app, BBQ, bestseller, blog, brand new, clear-cut, customs, cyberspace, download, easy-going, electronically, freshman, fulfilment, granted, graphically, high-tech, hotdog, ice cream, including, instal, ironically, laptop, living room, middle class, narrator, networking, online, ought to, owing to, planning, podcast, privatization, privatize, second hand, so-called, sparingly, stressful, telecommunications, webcast, website, well off, well-known, westerner, workforce

## Status interpretation

- `metadata_exact_unreviewed`: exact dictionary record found; metadata has not received human semantic review.
- `metadata_ambiguous`: multiple exact records found; none selected silently.
- `metadata_unmatched`: no exact dictionary record found; fields remain blank.
- `needs_review=yes`: metadata or future story context still requires review; it does not imply a failed exact match.

## Reproducibility

The full 62.9 MB ECDICT file is processed only in session scratch storage. The project retains the 6,127 matched records in `data/cet4_metadata_subset.jsonl` and the source/hash/count manifest in `data/cet4_metadata_manifest.json`.
