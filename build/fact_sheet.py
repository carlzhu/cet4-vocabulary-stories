"""Print the consolidated fact sheet used by the final reports."""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    provenance = json.loads(
        (ROOT / "reports" / "source_provenance.json").read_text(encoding="utf-8-sig")
    )
    print("provenance sources:")
    for name, item in sorted(provenance["sources"].items()):
        print(
            f"  {name}: {item['sha256'][:16]}... records={item.get('record_count', '-')}"
        )

    audit = json.loads((ROOT / "reports" / "qa_summary.json").read_text(encoding="utf-8-sig"))
    print()
    print("audit counts:", json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    print("audit problems:", audit["problems"])

    pdf = json.loads((ROOT / "reports" / "pdf_qa.json").read_text(encoding="utf-8-sig"))
    print()
    for volume in pdf["volumes"]:
        print(
            f"{volume['file']}: pages={volume['pages']} bytes={volume['bytes']} "
            f"a4={volume['a4_portrait']} blank={len(volume['blank_pages'])} "
            f"tofu={volume['replacement_glyphs']} "
            f"bounds={len(volume['boundary_violations'])} "
            f"embedded_paint={volume['all_painted_text_uses_embedded_fonts']} "
            f"minchars={volume['minimum_extracted_characters']}"
        )

    checkpoint = json.loads(
        (ROOT / "drafts" / "batches" / "checkpoint.json").read_text(encoding="utf-8-sig")
    )
    print()
    print(
        "checkpoint batches:",
        checkpoint["validation_counts"]["batches"],
        "complete:",
        checkpoint["validation_counts"]["complete_chapters"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
