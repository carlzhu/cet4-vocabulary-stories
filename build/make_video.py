"""Turn each chapter's MP3 into an MP4 with a title card and burned-in subtitles.

Where the timing comes from
---------------------------
Subtitles need to know when each sentence is spoken. Nothing has to be guessed or
aligned by hand:

* ``edge-tts`` would emit timings directly, but the delivered narration uses the
  offline SAPI voice, which does not.
* SAPI's ``SpeakProgress`` event reports, for every word, its character position and
  its ``AudioPosition`` - the offset into the audio being produced. That is the
  timing source.
* Those positions index the **SSML string**, not the plain text, and HTML escaping
  shifts them (``University's`` becomes ``University&#x27;s``). ``make_audio``
  therefore returns each paragraph's offset inside the SSML it builds, and this tool
  maps the events onto sentence ranges using those offsets.

Why the timings are valid for the committed MP3s: SAPI synthesis is deterministic for
a given voice, rate and SSML, and ``make_audio``'s SSML is byte-identical to the one
that produced the audio. Both were checked rather than assumed - re-running the
pipeline reproduces ``CH001.mp3`` byte-for-byte, and its decoded PCM matches. The
timing pass therefore needs no audio output at all.

Usage:
    python build/make_video.py                    # timings + all 137 MP4s
    python build/make_video.py --timings-only
    python build/make_video.py --chapters CH001-CH003
    python build/make_video.py --verify-only
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
sys.path.insert(0, str(ROOT / "build"))

from make_audio import (  # noqa: E402
    DEFAULT_RATE,
    DEFAULT_VOICE,
    load_chapters,
    powershell,
    ssml_for_parts,
)

AUDIO_DIR = ROOT / "build" / "audio"
VIDEO_DIR = ROOT / "build" / "video"
TIMING_DIR = VIDEO_DIR / "_timings"
# Kept out of VIDEO_DIR on purpose. A player that finds CH001.srt next to CH001.mp4
# loads it automatically and draws it on top of the burned-in subtitles, so the same
# sentence appears twice in two different styles. These are sidecars for re-muxing,
# not something a viewer should have to switch off.
SUBTITLE_DIR = VIDEO_DIR / "subtitles"
CARD_DIR = VIDEO_DIR / "cards"
MANIFEST = VIDEO_DIR / "video_manifest.json"
PLAN_CSV = ROOT / "curriculum_plan.csv"

VIDEO_W, VIDEO_H = 960, 540
# Burned-in subtitles are re-encoded on every frame, which dominates both size and
# time - a genuinely static image would compress to almost nothing, but the text does
# not. Measured per chapter: 1280x720 veryfast CRF 30 took 114 s and 1.9 MB, while
# 960x540 at 5 fps with ultrafast takes about 15 s for a similar size. Lowering the
# frame rate raises the bits per frame but cuts the frame count, which is the trade
# that pays here.
VIDEO_FPS = 5
VIDEO_CRF = 32
# Subtitles appear this many seconds before their sentence is spoken, so a learner can
# read ahead rather than read along. Applied to the shared boundaries between cues, so
# the timeline stays tiled: no overlaps, no gaps.
LEAD_IN_SECONDS = 1.5
CARD_BAND_Y = int(490 * VIDEO_H / 720)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
TOTAL_CHAPTERS = 137


def arc_lookup() -> dict[str, str]:
    """Map chapter id to 'Arc n · Chapter m of 137' from the protected plan."""

    lookup: dict[str, str] = {}
    if not PLAN_CSV.is_file():
        return lookup
    with PLAN_CSV.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            # The protected plan names this column article_id, not chapter_id.
            chapter_id = (row.get("article_id") or "").strip()
            arc = (row.get("arc_number") or "").strip()
            number = (row.get("chapter_number") or "").strip()
            if chapter_id:
                lookup[chapter_id] = f"Arc {arc}  ·  Chapter {number} of {TOTAL_CHAPTERS}"
    return lookup


def collect_timings(chapters: list[dict[str, object]]) -> None:
    """Speak every chapter and record word positions and audio offsets.

    One PowerShell process for the whole run: loading System.Speech costs about a
    second, which across 137 chapters would dominate the work.
    """

    TIMING_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ssml_dir = Path(tmp)

        def quote(value: object) -> str:
            return str(value).replace("'", "''")

        script = [
            "Add-Type -AssemblyName System.Speech",
            "$v = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            f"$v.SelectVoice('{quote(DEFAULT_VOICE)}'); $v.Rate = {DEFAULT_RATE}",
            # No audio output is needed, only the events.
            "$v.SetOutputToNull()",
            # ONE handler for the whole run, writing into a buffer that is cleared per
            # chapter. Registering a handler inside the loop added a new one each
            # chapter without removing the previous, so chapter N recorded N copies of
            # every event - 23,936 lines for a 350-word chapter.
            "$buf = New-Object System.Collections.ArrayList",
            "$v.add_SpeakProgress({ param($s, $e) "
            "[void]$buf.Add(\"$($e.CharacterPosition)`t$($e.AudioPosition.TotalSeconds)\") })",
        ]
        for chapter in chapters:
            chapter_id = str(chapter["article_id"])
            ssml = ssml_dir / f"{chapter_id}.ssml"
            ssml.write_text(
                ssml_for_parts(chapter, DEFAULT_VOICE, DEFAULT_RATE)[0], encoding="utf-8"
            )
            out = TIMING_DIR / f"{chapter_id}.txt"
            script += [
                "$buf.Clear()",
                f"$v.SpeakSsml([System.IO.File]::ReadAllText('{quote(ssml)}'))",
                f"[System.IO.File]::WriteAllLines('{quote(out)}', $buf)",
            ]
        script.append("$v.Dispose()")
        script_file = ssml_dir / "timings.ps1"
        script_file.write_text("\n".join(script), encoding="utf-8")
        started = time.time()
        result = subprocess.run(
            [powershell(), "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(script_file)],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        raise SystemExit(f"timing pass failed:\n{result.stderr[-2000:]}")
    print(f"  timings captured for {len(chapters)} chapters in {time.time() - started:.0f} s")


def load_events(chapter_id: str) -> list[tuple[int, float]]:
    path = TIMING_DIR / f"{chapter_id}.txt"
    if not path.is_file():
        return []
    events: list[tuple[int, float]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            try:
                events.append((int(parts[0]), float(parts[1])))
            except ValueError:
                continue
    events.sort(key=lambda pair: pair[1])
    return events


def detect_silences(mp3: Path) -> list[tuple[float, float]]:
    """Return (start, end) for every pause of at least 0.4 s in the narration."""

    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(mp3),
         "-af", "silencedetect=noise=-45dB:d=0.4", "-f", "null", "NUL"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    return list(zip(starts, ends))


def clock_fit(
    events: list[tuple[int, float]],
    parts: list[tuple[int, str]],
    breaks: list[tuple[float, float]],
) -> tuple[float, float, float, int]:
    """Fit ``audio_time = scale * event_time + offset`` from paragraph anchors.

    Each paragraph after the first begins at a known audio time - the end of a pause
    of at least 1.5 s - and its first word has a known event time, so those are
    anchor pairs. Fitting them shows the event clock is a *constant* multiple of real
    time: measured on five chapters the scale is 0.7255-0.7256 with a maximum residual
    of 4-10 ms.

    0.725625 is 16000/22050, so SAPI reports ``AudioPosition`` against a 16 kHz stream
    while the audio is written at 22.05 kHz - the earlier reading of 1.366 was wrong
    because it divided by the *start* of the final word rather than the end of the
    audio.

    The scale is fitted rather than hard-coded so that a change in the output format
    would be caught by the residual instead of silently skewing every subtitle.
    """

    pairs: list[tuple[float, float]] = []
    for index in range(1, len(parts)):
        if index - 1 >= len(breaks):
            break
        offset = parts[index][0]
        first = next((t for pos, t in events if pos >= offset), None)
        if first is not None:
            pairs.append((first, breaks[index - 1][1]))

    if len(pairs) < 3:
        return 16000 / 22050, 0.0, 0.0, len(pairs)

    n = len(pairs)
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    sxx = sum(x * x for x, _ in pairs)
    sxy = sum(x * y for x, y in pairs)
    denominator = n * sxx - sx * sx
    if denominator == 0:
        return 16000 / 22050, 0.0, 0.0, len(pairs)
    scale = (n * sxy - sx * sy) / denominator
    intercept = (sy - scale * sx) / n
    residual = max(abs(scale * x + intercept - y) for x, y in pairs)
    return scale, intercept, residual, len(pairs)


def sentence_cues(
    chapter: dict[str, object],
    events: list[tuple[int, float]],
    scale: float,
    offset: float,
    duration: float,
    lead_in: float,
) -> list[tuple[float, float, str]]:
    """Build (start, end, text) cues, one sentence each, on the fitted clock.

    ``lead_in`` shows each subtitle before its sentence is spoken, so a learner can
    read ahead instead of reading along. It is applied to the sentence boundaries
    rather than to each cue independently: cue k ends exactly where cue k+1 begins, so
    shifting the shared boundary keeps the timeline tiled - subtitles never overlap and
    never leave a gap. Shifting both ends of a cue instead would make it vanish before
    its sentence finished.
    """

    _ssml, parts = ssml_for_parts(chapter, DEFAULT_VOICE, DEFAULT_RATE)
    timed: list[tuple[float, str]] = []

    for paragraph_offset, escaped in parts:
        sentences = [s for s in SENTENCE_SPLIT.split(escaped) if s.strip()]
        cursor = paragraph_offset
        for sentence in sentences:
            start = cursor
            end = cursor + len(sentence)
            cursor = end + 1  # the whitespace the split consumed
            hit = next((t for pos, t in events if start <= pos < end), None)
            if hit is not None:
                timed.append((scale * hit + offset, html.unescape(sentence.strip())))

    result: list[tuple[float, float, str]] = []
    for index, (spoken_at, text) in enumerate(timed):
        start = max(0.0, spoken_at - lead_in)
        if index + 1 < len(timed):
            end = max(start + 0.2, timed[index + 1][0] - lead_in)
        else:
            # Nothing follows, so let the last line stand until the audio ends.
            end = max(start + 0.2, duration - 0.05)
        result.append((start, end, text))
    return result


def srt_timestamp(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    blocks = []
    for index, (start, end, text) in enumerate(cues, start=1):
        blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def card_for(chapter: dict[str, object], arc_line: str, pace: str) -> Path:
    """Render the still frame: chapter identity on top, a clear band for subtitles."""

    from PIL import Image, ImageDraw, ImageFont

    def font(size: int, bold: bool = False):
        for name in (
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/simhei.ttf",
        ):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    scale = VIDEO_H / 720
    image = Image.new("RGB", (VIDEO_W, VIDEO_H), (20, 52, 78))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, VIDEO_W, 8], fill=(46, 97, 124))
    draw.text((70 * scale, 110 * scale), str(chapter["article_id"]),
              font=font(int(34 * scale), True), fill=(140, 200, 225))
    draw.text((70 * scale, 168 * scale), str(chapter["english_title"]),
              font=font(int(50 * scale), True), fill=(255, 255, 255))
    draw.text((70 * scale, 250 * scale), "CET-4 Vocabulary Stories",
              font=font(int(28 * scale)), fill=(205, 225, 238))
    draw.text((70 * scale, 292 * scale), arc_line,
              font=font(int(24 * scale)), fill=(165, 198, 218))
    draw.text((70 * scale, 332 * scale), pace,
              font=font(int(24 * scale)), fill=(150, 190, 215))
    draw.text(
        (70 * scale, 380 * scale),
        "Subtitles: one sentence per cue, timed from the speech engine",
        font=font(int(21 * scale)),
        fill=(132, 172, 198),
    )
    draw.rectangle([0, CARD_BAND_Y, VIDEO_W, VIDEO_H], fill=(11, 32, 50))
    draw.rectangle([0, CARD_BAND_Y, VIDEO_W, CARD_BAND_Y + 3], fill=(46, 97, 124))

    path = CARD_DIR / f"{chapter['article_id']}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


class OutputLocked(RuntimeError):
    """The destination file could not be replaced because something holds it open."""


def mux(mp3: Path, card: Path, srt: Path, out: Path, duration: float) -> None:
    style = (
        "FontName=Arial,FontSize=14,PrimaryColour=&H00FFFFFF,OutlineColour=&H00202020,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=26,MarginL=52,MarginR=52"
    )
    # Write beside the destination and swap it in, so a viewer holding the finished
    # file open cannot break a whole run: the first attempt at this died on chapter 1
    # because the demo was still playing. If the swap fails the chapter is reported
    # and skipped, and everything else still builds.
    partial = out.with_name(out.stem + ".partial.mp4")
    # ffmpeg's filter parser treats ':' as an option separator, so a Windows path like
    # D:/... breaks the subtitles filter. Running from the subtitle's own directory and
    # passing only the file name avoids the drive colon entirely.
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(card),
            "-i", str(mp3),
            "-vf", f"subtitles={srt.name}:force_style='{style}'",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-crf", str(VIDEO_CRF), "-r", str(VIDEO_FPS), "-g", "600",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k",
            # -shortest is not reliable against a looped still image: the output ran
            # about three seconds long. Capping at the audio duration is exact.
            "-t", f"{duration:.3f}", str(partial),
        ],
        check=True,
        cwd=str(srt.parent),
    )
    try:
        os.replace(partial, out)
    except PermissionError as error:
        partial.unlink(missing_ok=True)
        raise OutputLocked(str(error)) from error


def sync_report(
    cues: list[tuple[float, float, str]], silences: list[tuple[float, float]]
) -> tuple[int, float]:
    """Flag cues whose span is mostly silence, which is what gross desync looks like.

    Comparing each cue start against the nearest pause *end* was tried and abandoned:
    SAPI also pauses mid-sentence at commas, so more than one pause end sits inside a
    sentence and the "nearest" one is regularly the wrong reference. Measuring how
    much of each cue's own span is silence needs no such correspondence and still
    catches a timeline that has drifted away from the speech.

    Correlation between cue length and sentence length is deliberately not the check:
    it is scale-invariant, so it stays high even when the whole timeline is stretched.
    """

    if not cues:
        return 0, 0.0
    worst = 0.0
    bad = 0
    for start, end, _text in cues:
        span = max(end - start, 1e-6)
        silent = sum(
            max(0.0, min(end, s_end) - max(start, s_start))
            for s_start, s_end in silences
        )
        fraction = silent / span
        worst = max(worst, fraction)
        if fraction > 0.6:
            bad += 1
    return bad, worst


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def main(argv: list[str]) -> int:
    global VIDEO_DIR, TIMING_DIR, SUBTITLE_DIR, CARD_DIR

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", default="")
    parser.add_argument("--out", default=str(VIDEO_DIR))
    parser.add_argument("--timings-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--lead-in",
        type=float,
        default=LEAD_IN_SECONDS,
        help="show each subtitle this many seconds before its sentence is spoken",
    )
    args = parser.parse_args(argv[1:])

    VIDEO_DIR = Path(args.out)
    TIMING_DIR = VIDEO_DIR / "_timings"
    SUBTITLE_DIR = VIDEO_DIR / "subtitles"
    CARD_DIR = VIDEO_DIR / "cards"

    chapters = load_chapters()
    if len(chapters) != TOTAL_CHAPTERS:
        print(f"WARNING: found {len(chapters)} chapters, expected {TOTAL_CHAPTERS}")
    if args.chapters:
        wanted: set[str] = set()
        for part in args.chapters.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                wanted.update(f"CH{n:03d}" for n in range(int(low[2:]), int(high[2:]) + 1))
            else:
                wanted.add(part)
        chapters = [c for c in chapters if str(c["article_id"]) in wanted]

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is required and was not found on PATH")

    arcs = arc_lookup()
    print(f"chapters : {len(chapters)}")
    print(f"output   : {VIDEO_DIR}")
    print(f"video    : {VIDEO_W}x{VIDEO_H}, burned-in subtitles, CRF 30")

    if not args.verify_only:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        print("timings  :")
        collect_timings(chapters)
        if args.timings_only:
            return 0

    started = time.time()
    problems: list[str] = []
    locked: list[str] = []
    records: list[dict[str, object]] = []
    for index, chapter in enumerate(chapters, start=1):
        chapter_id = str(chapter["article_id"])
        mp3 = AUDIO_DIR / f"{chapter_id}.mp3"
        out = VIDEO_DIR / f"{chapter_id}.mp4"
        if not mp3.is_file():
            problems.append(f"{chapter_id}: missing audio {mp3.name}")
            continue
        duration = probe_duration(mp3)
        events = load_events(chapter_id)
        if not events:
            problems.append(f"{chapter_id}: no timing events captured")
            continue
        silences = detect_silences(mp3)
        paragraph_count = len(chapter["english_paragraphs"])  # type: ignore[arg-type]
        paragraph_breaks = [s for s in silences if s[1] - s[0] >= 1.5]
        if len(paragraph_breaks) != paragraph_count - 1:
            problems.append(
                f"{chapter_id}: found {len(paragraph_breaks)} paragraph breaks in the "
                f"audio, expected {paragraph_count - 1}"
            )
        _ssml, parts = ssml_for_parts(chapter, DEFAULT_VOICE, DEFAULT_RATE)
        scale, offset, residual, anchors = clock_fit(events, parts, paragraph_breaks)
        if anchors and residual > 0.15:
            problems.append(
                f"{chapter_id}: clock fit residual {residual:.3f}s over {anchors} "
                f"anchors - the event clock is not a constant multiple of real time"
            )
        cues = sentence_cues(chapter, events, scale, offset, duration, args.lead_in)
        if not cues:
            problems.append(f"{chapter_id}: no subtitle cues derived")
            continue
        card = card_for(chapter, arcs.get(chapter_id, "Arc —"), "Narration: offline synthetic voice")
        srt = SUBTITLE_DIR / f"{chapter_id}.srt"
        srt.parent.mkdir(parents=True, exist_ok=True)
        write_srt(srt, cues)
        try:
            mux(mp3, card, srt, out, duration)
        except OutputLocked:
            locked.append(chapter_id)
            continue
        video_duration = probe_duration(out)
        mostly_silent, worst_silent = sync_report(cues, silences)
        records.append({
            "chapter_id": chapter_id,
            "cues": len(cues),
            "lead_in_seconds": args.lead_in,
            "clock_anchors": anchors,
            "clock_scale": round(scale, 6),
            "clock_offset": round(offset, 3),
            "clock_max_residual": round(residual, 4),
            "cues_mostly_silent": mostly_silent,
            "worst_silent_fraction": round(worst_silent, 2),
            "audio_seconds": round(duration, 2),
            "video_seconds": round(video_duration, 2),
            "first_cue": round(cues[0][0], 2),
            "last_cue_end": round(cues[-1][1], 2),
            "bytes": out.stat().st_size,
        })
        if mostly_silent > max(1, len(cues) // 10):
            problems.append(
                f"{chapter_id}: {mostly_silent}/{len(cues)} cues sit mostly in silence"
            )
        # AAC priming adds a fraction of a second; more than that means a real mismatch.
        if abs(video_duration - duration) > 1.5:
            problems.append(
                f"{chapter_id}: video {video_duration:.1f}s vs audio {duration:.1f}s"
            )
        if cues[-1][1] > duration + 0.2:
            problems.append(f"{chapter_id}: last cue ends at {cues[-1][1]:.1f}s, past the audio")
        if index % 20 == 0 or index == len(chapters):
            print(f"  {index}/{len(chapters)} built")

    if records:
        total = sum(int(r["bytes"]) for r in records)
        print(f"  built        : {len(records)} videos in {time.time() - started:.0f} s")
        print(f"  total size   : {total/1024/1024:.1f} MB "
              f"({total/len(records)/1024/1024:.2f} MB each)")
        print(f"  cues min/max : {min(int(r['cues']) for r in records)}"
              f" / {max(int(r['cues']) for r in records)}")
        MANIFEST.write_text(
            json.dumps({
                "video": {"width": VIDEO_W, "height": VIDEO_H, "crf": 30,
                          "subtitle": "burned in, one sentence per cue"},
                "timing_source": (
                    "SAPI SpeakProgress AudioPosition, mapped onto sentence ranges via "
                    "the SSML character offsets from make_audio.ssml_for_parts"
                ),
                "chapters": records,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  manifest     : {MANIFEST.relative_to(ROOT)}")

    if locked:
        print(f"SKIPPED ({len(locked)}) - the file was open in another program, so it "
              f"could not be replaced. Close it and re-run; {len(locked)} chapter(s) "
              f"still need building:")
        for chapter_id in locked[:20]:
            print("  -", chapter_id)

    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for problem in problems[:30]:
            print("  -", problem)
        return 1
    if locked:
        return 2
    print("  all videos verified: duration matches the audio, cues inside the timeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
