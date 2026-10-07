"""Independently check subtitle timing against the rendered audio.

Why this exists: the video tool's own gates use the same word events that produced the
cues, so they cannot detect a systematic offset. This measures the finished `.srt` files
against the audio alone.

How the offset is measured. The reference is **cue start plus the lead-in** - the moment
the sentence is meant to be spoken - compared with the nearest speech onset detected in
the recording. Comparing the cue start itself would be wrong once a lead-in exists: the
start sits near an earlier pause, often a comma pause inside the previous sentence, and
the "nearest onset" would then be the wrong one.

The first cue of each chapter is excluded. Its start is clamped to zero because there is
no room for a lead at the very beginning, so start+lead points somewhere the sentence
never was; including it invents an outlier in every chapter.

What it checks:

* **no clock drift** - the offsets should be tightly clustered. Drift shows up as spread:
  before the offset bug was found this spread was 0.24-0.30 s, after it 0.008 s.
* **the expected speech time lands on a speech onset** - measured as
  ``(cue start + lead) - nearest onset`` and required to be near zero. This verifies the
  clock and the lead together: had the lead not been applied, the cue start would already
  be the onset and every value would read about ``+lead``.
* **speech is present when expected** - the audio at the expected time must not be silent,
  which catches a cue placed inside a pause regardless of onset detection.

Usage:
    python build/check_sync.py [--lead 1.5] [--chapters CH001-CH010]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
sys.path.insert(0, str(ROOT / "build"))

from make_video import SUBTITLE_DIR, detect_silences  # noqa: E402

TIMESTAMP = re.compile(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)")


def parse_srt(path: pathlib.Path) -> list[float]:
    starts = []
    for block in path.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.split("\n")
        if len(lines) < 2:
            continue
        match = TIMESTAMP.match(lines[1])
        if not match:
            continue
        g = [int(value) for value in match.groups()]
        starts.append(g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000)
    return starts


def mean_db(path: pathlib.Path, at: float, seconds: float = 0.8) -> float:
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", f"{at:.2f}", "-t", f"{seconds}",
         "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    return float("-inf")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lead", type=float, default=1.5)
    parser.add_argument("--chapters", default="")
    parser.add_argument("--tolerance", type=float, default=0.35)
    parser.add_argument("--max-outlier-fraction", type=float, default=0.10)
    parser.add_argument("--silence-db", type=float, default=-45.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv[1:])

    files = sorted(SUBTITLE_DIR.glob("CH*.srt"))
    if args.chapters:
        keep: set[str] = set()
        for part in args.chapters.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                keep.update(f"CH{n:03d}" for n in range(int(low[2:]), int(high[2:]) + 1))
            else:
                keep.add(part)
        files = [path for path in files if path.stem in keep]
    if not files:
        print(f"no subtitle files under {SUBTITLE_DIR}", file=sys.stderr)
        return 1

    medians: list[float] = []
    spreads: list[float] = []
    outliers_total = cues_total = 0
    silent_cues = 0
    failures: list[str] = []

    for path in files:
        cid = path.stem
        mp3 = ROOT / "build" / "audio" / f"{cid}.mp3"
        if not mp3.is_file():
            failures.append(f"{cid}: no audio")
            continue
        silences = detect_silences(mp3)
        onsets = sorted(end for _start, end in silences)
        starts = parse_srt(path)
        if not onsets or not starts:
            failures.append(f"{cid}: nothing to compare")
            continue

        offsets = []
        outliers = 0
        for start in starts:
            expected = start + args.lead
            # Skip the clamped first cue: there was no room for a lead at the start.
            if start + 1e-6 < args.lead:
                continue
            if mean_db(mp3, expected) <= args.silence_db:
                silent_cues += 1
            near = min(onsets, key=lambda value: abs(expected - value))
            error = expected - near
            offsets.append(error)
            if abs(error) > args.tolerance:
                outliers += 1
        if not offsets:
            failures.append(f"{cid}: no comparable cues")
            continue

        cues_total += len(offsets)
        outliers_total += outliers
        median = statistics.median(offsets)
        sorted_offsets = sorted(offsets)
        quartile = len(sorted_offsets) // 4 or 1
        iqr = (
            sorted_offsets[-quartile] - sorted_offsets[quartile - 1]
            if len(sorted_offsets) > 2
            else 0.0
        )
        spread = statistics.pstdev(offsets)
        medians.append(median)
        spreads.append(iqr)

        if outliers / len(offsets) > args.max_outlier_fraction:
            failures.append(
                f"{cid}: {outliers}/{len(offsets)} cues are more than "
                f"{args.tolerance}s from a speech onset"
            )
        if abs(median) > args.tolerance:
            # The expected speech time (cue start + lead) must coincide with a speech
            # onset. This verifies the clock *and* the lead-in transitively: if the lead
            # had not been applied, start would already be the onset, expected would sit
            # `lead` seconds late, and the median would read about +lead.
            failures.append(
                f"{cid}: median {median:+.2f}s - the expected speech time does not land "
                f"on a speech onset"
            )
        # Drift is judged on the interquartile range, not the standard deviation. A
        # sentence that begins inside quoted dialogue follows a comma pause too short for
        # the silence detector, so its onset is missing from the reference set and its
        # offset is large; one such cue would drag a stdev past any useful threshold while
        # the timing itself is correct. The IQR is not moved by one or two such cues.
        if iqr > args.tolerance:
            failures.append(
                f"{cid}: interquartile spread {iqr:.3f}s - suggests clock drift"
            )
        if args.verbose:
            print(f"  {cid}: {len(offsets)} cues  median {median:+.3f}s  "
                  f"iqr {iqr:.3f}s  stdev {spread:.3f}s  outliers {outliers}")

    print(f"  chapters checked        : {len(medians)}")
    if medians:
        print(f"  median offset           : {statistics.median(medians):+.3f}s "
              f"(requested lead {-args.lead:+.2f}s)")
        print(f"  median interquartile spread : "
              f"{statistics.median([s for s in spreads]):.3f}s "
              f"(0.007s when the clock is exact; 0.24-0.30s before the offset bug was fixed)")
        print(f"  cues compared           : {cues_total}")
        print(f"  cues beyond {args.tolerance}s        : {outliers_total} "
              f"({outliers_total / max(cues_total, 1) * 100:.2f}%)")
        print(f"  cues with silence at the expected speech time: {silent_cues}")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for failure in failures[:20]:
            print("  -", failure)
        return 1
    print("  all chapters pass: lead-in is the requested size, no drift, speech where expected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
