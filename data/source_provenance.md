# CET-4 Vocabulary Source Provenance

## Selected source

- Official syllabus page: https://cet.neea.edu.cn/html1/folder/16113/1588-1.htm
- Official syllabus PDF: https://cet.neea.edu.cn/res/Home/1704/55b02330ac17274664f06d9d3db8249d.pdf
- Official document: 《全国大学英语四、六级考试大纲（2016年修订版）》
- Official PDF SHA-256 observed on 2026-10-06: `9166d3c03b7bc43abd9d9df91bd2ef8085b4419286f1e5ca100dea68f3cfd1f1`
- Machine-readable transcription: https://github.com/ismartcoding/endict
- Pinned repository commit: `522c17036976c34c994a1d367bd61a7d9fa495d9`
- Selected file: https://github.com/ismartcoding/endict/blob/522c17036976c34c994a1d367bd61a7d9fa495d9/vocabulary/cet4.json
- Selected file SHA-256: `50143a67069cd69c0ce1221a6f7bb554b992b3295322344907bf784afb5ff9c0`
- Repository license: MIT, copyright 2022 SmartCoding
- Download date: 2026-10-06

## Selection rationale

The official syllabus states that its combined CET-4/CET-6 list contains 5,418 headword groups, with CET-6 items marked by `★`. It lists forms only and intentionally provides no part of speech, meaning, or pronunciation.

The selected repository explicitly states that its CET-4/CET-6 lists were transcribed from that 2016 syllabus and separates the non-starred CET-4 forms into `cet4.json`. It expands word-family groups and parallel spellings into individual forms. This produces 6,127 unique CET-4 forms rather than roughly 4,500 grouped entries. The expanded form count is used because this project must not automatically merge derived words or same-root words.

## Cross-checks

- Selected CET-4 file: 6,127 rows; 6,127 case-insensitive unique forms; 0 duplicate rows.
- Companion CET-6 file: 1,715 unique forms.
- CET-4/CET-6 overlap: 4 forms (`appropriate`, `converse`, `invalid`, `staple`), consistent with homographs or classification ambiguity requiring review.
- Combined expanded forms: 7,838 unique forms.
- A separate GitHub list advertised as “4505 words” was rejected as the primary source: it contains 4,427 case-insensitive unique forms and 78 duplicate rows, and its repository provides neither source provenance nor an explicit license.

## Known limitations

1. The repository is a third-party machine-readable transcription, not an official data API.
2. The 6,127 figure counts expanded forms, not the official document's grouped “词目” count.
3. The official list supplies no POS, Chinese meaning, phonetics, or frequency. These fields must remain blank until separately sourced and reviewed.
4. The four CET-4/CET-6 overlapping forms and multiword/spelling variants require rule-based or human review.
5. Coverage statistics must use the imported file hash and never claim that the third-party transcription itself is an official published JSON list.


## Metadata source

- Upstream dictionary: https://github.com/skywind3000/ECDICT
- Selected file: `ecdict.csv`
- Downloaded size: 65,933,428 bytes
- Content SHA-256: `1a6947e04785db63613a92e14903cdae7954f7e84860b10e68e5c7cbb3f9c3cf`
- License: MIT
- Rows scanned: 770,611
- Exact CET-4 target matches retained: 6,127

ECDICT supplies third-party Chinese translations, phonetics, definitions, tags, frequencies, and inflections. These fields are provenance-labelled and are not described as official CET data. The complete ECDICT CSV remains in session scratch storage; only exact target records are retained in the project.
