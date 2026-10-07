# A4 Layout Capacity Report

## Tested configuration

- Paper: A4 portrait, 595.28 × 841.89 pt
- Margins: 15 mm story pages; 18 mm exercise/answer pages
- English body: Arial 9.4 pt, 13.1 pt leading
- Chinese body: SimHei 8.8 pt, 13 pt leading
- Vocabulary table: SimHei 6.7 pt, 8 pt leading
- New targets: dark blue bold
- Review targets: teal italic underline
- Main text color: dark chromatic blue rather than pure black, for color-cartridge printing

## Sample measurements

| Sample | English words | New targets | Context reviews | Story pages | Exercise pages |
|---|---:|---:|---:|---:|---:|
| CH001 long-body case | 401 | 45 | 0 | 3 | 1 |
| CH050 translation/table case | 399 | 45 | 18 | 3 | 1 |
| CH090 technical/exercise case | 361 | 45 | 18 | 3 | 1 |

Each tested chapter requires one story/translation page and two vocabulary-table pages. An earlier table layout produced sparse fourth pages; font size, line spacing, cell padding, and source-example length were adjusted without shrinking the story text. The repaired output is consistently three pages per chapter.

## Full-course estimate

- Planned chapters: 137
- Story/vocabulary PDF: approximately 411 pages
- Exercise PDF: approximately 137 pages
- Answer key: approximately 35 pages

These are planning estimates, not final page-count claims. Actual final counts must be read from generated PDFs.

## Automated PDF checks

- Story samples: 9 pages, all A4 portrait, no blank page
- Exercise samples: 3 pages, all A4 portrait, no blank page
- Answer samples: 1 page, A4 portrait, no blank page
- Chinese replacement characters: 0
- Arial, Arial Bold, and SimHei: embedded TrueType subsets
- Standard Helvetica remains as an unused/base PDF resource and is not relied upon for content

## Visual inspection

Rendered contact sheets were inspected for all 13 pages. No overlap, clipping, table overflow, missing body text, or accidental blank page was observed. Two initially sparse vocabulary spill pages were detected and eliminated. Mixed English/Chinese headings initially showed missing Chinese glyphs under Arial; both headings were switched explicitly to embedded SimHei and visually rechecked.

No physical printer test has been performed. The printer driver must be set to color mode so it does not substitute the unavailable black cartridge.
