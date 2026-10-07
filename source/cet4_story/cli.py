from __future__ import annotations

import argparse
import json
from pathlib import Path

from cet4_story.batch import (
    DEFAULT_BATCH_SIZE,
    commit_batch,
    completed_chapter_ids,
    continuity_path,
    load_batch,
    load_checkpoint,
    next_batch_chapter_ids,
    rebuild_checkpoint,
    record_boundary,
    validate_batch,
    verify_batch_integrity,
)
from cet4_story.continuity import load_continuity
from cet4_story.enrichment import (
    DEFAULT_COMMIT,
    enrich_from_ecdict_csv,
    run_shard_enrichment,
)
from cet4_story.planner import plan_curriculum
from cet4_story.pdf_builder import DEFAULT_PREVIEW_DIR, build_preview
from cet4_story.project_data import load_project, verify_invariants
from cet4_story.reporting import (
    COVERAGE_CSV_PATH,
    QA_SUMMARY_PATH,
    audit_curriculum,
    write_coverage_csv,
    write_manuscript,
    write_qa_summary,
)
from cet4_story.sample_builder import (
    build_sample_pdfs,
    inspect_sample_pdfs,
    verify_samples,
)
from cet4_story.vocabulary import discover_candidates, import_vocabulary
from cet4_story.workpack import render_batch_workpack, resolve_chapter_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CET-4 vocabulary story build system")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inspect", help="List vocabulary-source candidates")
    import_parser = subparsers.add_parser("import-vocabulary", help="Normalize a confirmed source")
    import_parser.add_argument("source", type=Path)

    csv_parser = subparsers.add_parser(
        "enrich-ecdict-csv", help="Exact-match targets against an ECDICT CSV file"
    )
    csv_parser.add_argument("source", type=Path)
    csv_parser.add_argument("--expected-sha256")

    shard_parser = subparsers.add_parser(
        "enrich-endict-shards", help="Fallback: download and exact-match endict JSONL shards"
    )
    shard_parser.add_argument("--commit", default=DEFAULT_COMMIT)
    shard_parser.add_argument("--scratch-root", type=Path)
    shard_parser.add_argument("--workers", type=int, default=8)
    shard_parser.add_argument("--shard-count", type=int, default=608)

    subparsers.add_parser(
        "plan-curriculum", help="Allocate all targets and create relative spaced reviews"
    )
    subparsers.add_parser("verify-samples", help="Verify sample text against planned targets")
    subparsers.add_parser("build-sample-pdfs", help="Generate three printable sample PDFs")
    subparsers.add_parser("inspect-sample-pdfs", help="Check sample PDF size and blank pages")

    subparsers.add_parser(
        "verify-sources", help="Verify protected sources, provenance, and invariants"
    )
    subparsers.add_parser(
        "checkpoint-status", help="Show the batch checkpoint and its integrity"
    )
    next_parser = subparsers.add_parser(
        "next-batch", help="Show the next chapters still to generate"
    )
    next_parser.add_argument("--size", type=int, default=DEFAULT_BATCH_SIZE)
    work_parser = subparsers.add_parser(
        "workpack", help="Render the generation brief for a chapter or range"
    )
    work_parser.add_argument("selector", help="next, CH002, or CH002-CH009")
    validate_parser = subparsers.add_parser(
        "validate-batch", help="Validate one batch document against the protected sources"
    )
    validate_parser.add_argument("path", type=Path)
    validate_parser.add_argument(
        "--no-continuity",
        action="store_true",
        help="Skip the batch-boundary continuity requirement (used for the samples)",
    )
    commit_parser = subparsers.add_parser(
        "commit-batch",
        help="Validate a batch, record its boundary record, and advance the checkpoint",
    )
    commit_parser.add_argument("path", type=Path)
    pdf_parser = subparsers.add_parser(
        "build-pdfs", help="Render available chapters to A4 story/exercise/answer PDFs"
    )
    pdf_parser.add_argument(
        "--selector", default="completed", help="completed, all, or a range such as CH002-CH017"
    )
    pdf_parser.add_argument("--out", type=Path, default=DEFAULT_PREVIEW_DIR)
    pdf_parser.add_argument("--prefix", default="CET4_Preview")
    pdf_parser.add_argument("--no-per-chapter", action="store_true")
    audit_parser = subparsers.add_parser(
        "audit-curriculum",
        help="Re-validate every chapter and write the coverage CSV and manuscript",
    )
    audit_parser.add_argument("--coverage-csv", type=Path)
    audit_parser.add_argument("--manuscript", type=Path)
    audit_parser.add_argument("--qa-summary", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.project_root.resolve()
    if args.command == "inspect":
        candidates = discover_candidates(root)
        print(json.dumps([str(path) for path in candidates], ensure_ascii=False, indent=2))
        return 0 if candidates else 2
    if args.command == "import-vocabulary":
        result = import_vocabulary(args.source, root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "enrich-ecdict-csv":
        result = enrich_from_ecdict_csv(
            root,
            args.source,
            expected_sha256=args.expected_sha256,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "enrich-endict-shards":
        result = run_shard_enrichment(
            root,
            scratch_root=args.scratch_root,
            commit=args.commit,
            workers=args.workers,
            shard_count=args.shard_count,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "plan-curriculum":
        result = plan_curriculum(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "verify-samples":
        result = verify_samples(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "build-sample-pdfs":
        result = build_sample_pdfs(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-sample-pdfs":
        result = inspect_sample_pdfs(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "verify-sources":
        project = load_project(root)
        summary = verify_invariants(project)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if args.command == "checkpoint-status":
        checkpoint = load_checkpoint(root)
        rebuilt = rebuild_checkpoint(root)
        payload = {
            "checkpoint": checkpoint.to_dict(),
            "rebuilt_from_disk": rebuilt.to_dict(),
            "completed_chapters": len(completed_chapter_ids(root)),
            "integrity_problems": verify_batch_integrity(root, checkpoint),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not payload["integrity_problems"] else 1
    if args.command == "next-batch":
        completed = completed_chapter_ids(root)
        pending = next_batch_chapter_ids(completed, batch_size=args.size)
        print(
            json.dumps(
                {
                    "completed_chapters": len(completed),
                    "remaining_chapters": 137 - len(completed),
                    "next_batch": list(pending),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if pending else 3
    if args.command == "workpack":
        project = load_project(root)
        chapter_ids = resolve_chapter_ids(project, args.selector)
        print(render_batch_workpack(project, chapter_ids))
        return 0
    if args.command == "validate-batch":
        project = load_project(root)
        batch = load_batch(args.path)
        states = load_continuity(continuity_path(root))
        previous = [
            state
            for chapter_id, state in sorted(states.items())
            if chapter_id < batch.chapter_ids[0]
        ]
        outcome = validate_batch(
            batch.chapters,
            project,
            batch_id=batch.batch_id,
            previous_state=previous[-1] if previous else None,
            current_state=batch.continuity,
            require_continuity=not args.no_continuity,
        )
        print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2))
        return 0 if outcome.result.is_valid else 1
    if args.command == "commit-batch":
        project = load_project(root)
        batch = load_batch(args.path)
        states = load_continuity(continuity_path(root))
        earlier = [
            state
            for chapter_id, state in sorted(states.items())
            if chapter_id < batch.chapter_ids[0]
        ]
        previous = earlier[-1] if earlier else None
        outcome = validate_batch(
            batch.chapters,
            project,
            batch_id=batch.batch_id,
            previous_state=previous,
            current_state=batch.continuity,
        )
        if not outcome.result.is_valid:
            print(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2))
            return 1
        if batch.continuity is not None:
            record_boundary(root, batch.continuity, previous_state=previous)
        checkpoint = commit_batch(root, batch, outcome)
        print(
            json.dumps(
                {
                    "batch": batch.to_dict(),
                    "checkpoint": checkpoint.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "build-pdfs":
        result = build_preview(
            root,
            selector=args.selector,
            out_dir=args.out,
            prefix=args.prefix,
            per_chapter=not args.no_per_chapter,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.command == "audit-curriculum":
        audit = audit_curriculum(root)
        coverage_path = write_coverage_csv(
            audit, args.coverage_csv or root / COVERAGE_CSV_PATH
        )
        manuscript_path = write_manuscript(root, args.manuscript)
        qa_path = write_qa_summary(
            audit,
            args.qa_summary or root / QA_SUMMARY_PATH,
            extra={
                "coverage_csv": str(coverage_path.relative_to(root)),
                "manuscript": str(manuscript_path.relative_to(root)),
                "human_review_pending": True,
            },
        )
        payload = audit.to_dict()
        payload["coverage_csv"] = str(coverage_path.relative_to(root))
        payload["manuscript"] = str(manuscript_path.relative_to(root))
        payload["qa_summary"] = str(qa_path.relative_to(root))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if audit.is_valid else 1
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
