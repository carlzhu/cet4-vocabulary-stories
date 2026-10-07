"""Apply Chinese translation (and arc-edge) patches to chapter files.

The generator appended English sentences to reach the 350-word floor without
translating them, leaving 331 English sentences with no Chinese counterpart. This
applies the missing translations, and the arc-edge lines, in one auditable step.

Patch format - a JSON object keyed by batch id ("sample_chapters" for the sample
file), whose value maps a chapter id to the edit:

    {
      "batch-CH002-CH005": {
        "CH002": {"paragraph": 5, "append_chinese": "……"},
        "CH003": {"paragraph": 5, "append_chinese": "……",
                  "append_english": "……"}
      }
    }

``append_chinese`` extends the Chinese paragraph; ``append_english`` extends the
English paragraph (used for arc-opening recaps and arc-closing echoes). Both are
inserted into the paragraph named by ``paragraph`` (1-based).

Every edit is verified after writing: the Chinese must cover the English, the
English word count must stay within 350-450, and paragraph counts must stay
aligned. A patch that would break any of those is rejected before it is saved.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

# Use the validator's own word counter. A naive str.split() counts standalone
# em-dashes and numerals as words, which made this gate stricter than the
# validator and rejected chapters that pass validation.
from cet4_story.validation import count_english_words  # noqa: E402

EN_SENTENCE = re.compile(r"[^.!?]+[.!?]+|[^.!?]*$")
CN_SENTENCE = re.compile(r"[^。！？；…]+[。！？；…]+|[^。！？；…]*$")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
MIN_WORDS = 350
MAX_WORDS = 450


def sentences(text: str, chinese: bool) -> int:
    pattern = CN_SENTENCE if chinese else EN_SENTENCE
    return sum(1 for piece in pattern.findall(text) if piece.strip())


def file_for(batch_id: str) -> Path:
    if batch_id == "sample_chapters":
        return ROOT / "drafts" / "sample_chapters.json"
    return ROOT / "drafts" / "batches" / f"{batch_id}.json"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    patch_path = Path(argv[1])
    patch = json.loads(patch_path.read_text(encoding="utf-8"))

    problems: list[str] = []
    notes: list[str] = []
    applied = 0
    files_written: list[str] = []

    for batch_id, edits in patch.items():
        path = file_for(batch_id)
        if not path.is_file():
            problems.append(f"{batch_id}: no such file {path}")
            continue
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        by_id = {entry["article_id"]: entry for entry in document["chapters"]}

        # Per-batch atomicity: a batch file is written only if every edit in it
        # passes, and the report says exactly which files changed.
        batch_ok = True

        for chapter_id, raw_edits in edits.items():
            entry = by_id.get(chapter_id)
            if entry is None:
                problems.append(f"{batch_id}/{chapter_id}: chapter not in file")
                batch_ok = False
                continue
            edit_list = raw_edits if isinstance(raw_edits, list) else [raw_edits]
            english = list(entry["english_paragraphs"])
            chinese = list(entry["chinese_paragraphs"])

            for edit in edit_list:
                index = int(edit["paragraph"]) - 1
                if not (0 <= index < len(english)):
                    problems.append(
                        f"{batch_id}/{chapter_id}: paragraph {index + 1} out of range"
                    )
                    batch_ok = False
                    break

                # Replacement and append are independent: a patch may replace a
                # paragraph and still append an arc-edge line to it. Treating them
                # as either/or silently dropped the append (and with it the Chinese
                # half of five arc-closing echoes).
                if edit.get("english"):
                    english[index] = edit["english"].strip()
                if edit.get("append_english"):
                    english[index] = english[index].rstrip() + " " + edit["append_english"].strip()
                if edit.get("chinese"):
                    chinese[index] = edit["chinese"].strip()
                if edit.get("append_chinese"):
                    chinese[index] = chinese[index].rstrip() + edit["append_chinese"].strip()

                # Surgical replacements, for editorial fixes where reproducing the
                # whole paragraph would invite transcription errors.
                for pair in edit.get("english_replace", []):
                    if pair["old"] not in english[index]:
                        problems.append(
                            f"{batch_id}/{chapter_id}: English text to replace not found: "
                            f"{pair['old']!r}"
                        )
                        batch_ok = False
                        break
                    english[index] = english[index].replace(pair["old"], pair["new"])
                for pair in edit.get("chinese_replace", []):
                    if pair["old"] not in chinese[index]:
                        problems.append(
                            f"{batch_id}/{chapter_id}: Chinese text to replace not found: "
                            f"{pair['old']!r}"
                        )
                        batch_ok = False
                        break
                    chinese[index] = chinese[index].replace(pair["old"], pair["new"])
                if not batch_ok:
                    break

                words_here = count_english_words({"english_paragraphs": [english[index]]})
                density = len(CJK.findall(chinese[index])) / words_here if words_here else 0.0
                if density < 1.2:
                    problems.append(
                        f"{batch_id}/{chapter_id}: paragraph {index + 1} density {density:.2f} < 1.2"
                    )
                    batch_ok = False
                # Reported, not gated: the English sentence regex splits quoted
                # sentences apart, so a faithful Chinese rendering that merges two
                # quoted clauses shows a phantom gap of two.
                gap = sentences(english[index], False) - sentences(chinese[index], True)
                if gap >= 2:
                    notes.append(
                        f"{batch_id}/{chapter_id}: paragraph {index + 1} sentence gap {gap} "
                        f"(density {density:.2f}) - advisory only"
                    )

            words = count_english_words({"english_paragraphs": english})
            if not (MIN_WORDS <= words <= MAX_WORDS):
                problems.append(
                    f"{batch_id}/{chapter_id}: word count {words} outside {MIN_WORDS}-{MAX_WORDS}"
                )
                batch_ok = False
            if len(english) != len(chinese):
                problems.append(f"{batch_id}/{chapter_id}: paragraph counts diverged")
                batch_ok = False
            if not batch_ok:
                continue

            entry["english_paragraphs"] = english
            entry["chinese_paragraphs"] = chinese
            applied += 1

        if batch_ok:
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            files_written.append(batch_id)
    print(f"edits validated : {applied}")
    print(f"files written   : {len(files_written)} -> {', '.join(files_written) or 'none'}")

    # Coverage must be re-checked here, not assumed. An editorial edit that removes
    # a mandated word silently breaks vocabulary coverage - replacing the profanity
    # in CH042 removed the target word "shit", and removing a first-person slip in
    # CH058 removed the review word "I". Both only surfaced on batch validation.
    from cet4_story.batch import validate_batch as _validate_batch  # noqa: PLC0415

    coverage_broken = False
    for batch_id in files_written:
        outcome = _validate_batch(ROOT, ROOT / "drafts" / "batches" / f"{batch_id}.json")
        if outcome.result.is_valid:
            print(f"  coverage OK     : {batch_id}")
            continue
        coverage_broken = True
        print(f"  COVERAGE BROKEN : {batch_id}")
        for error in list(outcome.result.errors)[:6]:
            print(f"      {error}")

    for note in notes:
        print("  note:", note)
    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for problem in problems:
            print("  -", problem)
        return 1
    return 1 if coverage_broken else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
