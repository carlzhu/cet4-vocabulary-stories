"""Generate one MP3 per chapter from the chapter sources, with verification.

Reads the English story text from the JSON sources - not from the PDFs, which would
mean extracting text back out of a rendering - and synthesizes it with the offline
Windows speech engine (SAPI), then encodes to MP3 with ffmpeg.

Why offline SAPI: this machine's route to the internet is unreliable, and SAPI needs
no network, no API key, and no extra dependency. The trade-off is voice quality: SAPI
sounds synthetic where a neural voice would not. `--voice` selects among the
installed voices.

Verification is part of the run, not a separate step. For every chapter it checks
that the file exists, that its duration matches the word count at a plausible
speaking rate (which catches truncated synthesis), and that a sample from the middle
of the file is not silence. Failures are reported and the exit code is non-zero.

Windows-only, like the PDF build: it needs System.Speech, ffmpeg on PATH, and the
installed voices.

Usage:
    python build/make_audio.py                     # all 137 chapters
    python build/make_audio.py --chapters CH001-CH005
    python build/make_audio.py --voice "Microsoft David Desktop" --rate 0
    python build/make_audio.py --verify-only
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))

BATCH_DIR = ROOT / "drafts" / "batches"
SAMPLES = ROOT / "drafts" / "sample_chapters.json"
OUT_DIR = ROOT / "build" / "audio"
MANIFEST = OUT_DIR / "audio_manifest.json"

DEFAULT_VOICE = "Microsoft Zira Desktop"
DEFAULT_RATE = -2  # 0 is ~170 wpm; -2 measured 124 wpm, a deliberate teaching pace
PARAGRAPH_PAUSE_MS = 700
TOTAL_CHAPTERS = 137

# A chapter is 350-450 words. These bounds are wide on purpose: they exist to catch
# truncated or bloated output, not to police pacing.
MIN_WPM, MAX_WPM = 60, 260


def load_chapters() -> list[dict[str, object]]:
    """Return all 137 chapters in reading order, from both sources."""

    chapters: list[dict[str, object]] = []
    for path in sorted(BATCH_DIR.glob("batch-*.json")):
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        chapters.extend(document["chapters"])
    if SAMPLES.is_file():
        document = json.loads(SAMPLES.read_text(encoding="utf-8-sig"))
        chapters.extend(document["chapters"])
    chapters.sort(key=lambda c: str(c["article_id"]))
    return chapters


def ssml_for(chapter: dict[str, object], voice: str, rate: int) -> str:
    paragraphs = [str(p) for p in chapter["english_paragraphs"]]  # type: ignore[index]
    body = f'<break time="{PARAGRAPH_PAUSE_MS}ms"/>'.join(
        f"<p>{html.escape(p)}</p>" for p in paragraphs
    )
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="en-US"><voice name="{html.escape(voice)}">'
        f'<prosody rate="{rate}">{body}</prosody></voice></speak>'
    )


def powershell() -> str:
    """Return the PowerShell executable to run the synthesis script.

    PowerShell 7 (`pwsh`) is not installed on every Windows box - this machine has
    only Windows PowerShell 5.1 - so both are tried. System.Speech is available in
    either.
    """

    for name in ("pwsh", "powershell"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("neither pwsh nor powershell was found on PATH")


def synthesize(wavs: list[tuple[Path, Path, str, int]], log: bool = True) -> float:
    """Synthesize every (ssml, wav) pair in one PowerShell process.

    One process, not one per chapter: loading System.Speech costs about a second,
    which would double the run time across 137 chapters.
    """

    def quote(value: object) -> str:
        return str(value).replace("'", "''")

    # One statement per chapter, rather than an array of hashtables: Windows
    # PowerShell 5.1 rejects a trailing comma in an array literal, and this is
    # simpler to read in the generated script.
    script_lines = ["Add-Type -AssemblyName System.Speech",
                    "$v = New-Object System.Speech.Synthesis.SpeechSynthesizer"]
    for ssml, wav, voice, rate in wavs:
        script_lines.append(
            f"$v.SelectVoice('{quote(voice)}'); $v.Rate = {rate}; "
            f"$v.SetOutputToWaveFile('{quote(wav)}'); "
            f"$v.SpeakSsml([System.IO.File]::ReadAllText('{quote(ssml)}'))"
        )
    script_lines.append("$v.Dispose()")

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "synth.ps1"
        script.write_text("\n".join(script_lines), encoding="utf-8")
        started = time.time()
        result = subprocess.run(
            [
                powershell(),
                "-NoProfile",
                "-NonInteractive",
                # Process-scoped only: a generated .ps1 is otherwise blocked by the
                # machine's execution policy, and this does not change that policy.
                "-ExecutionPolicy", "Bypass",
                "-File", str(script),
            ],
            capture_output=True,
            text=True,
        )
        elapsed = time.time() - started
    if result.returncode != 0:
        raise SystemExit(f"speech synthesis failed:\n{result.stderr[-2000:]}")
    if log:
        print(f"  synthesized {len(wavs)} chapters in {elapsed:.1f} s")
    return elapsed


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def mean_volume_db(path: Path, start: float, seconds: float = 15.0) -> float:
    """Mean volume of a slice, to catch silence without decoding whole files."""

    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", f"{start:.1f}", "-t", f"{seconds}",
         "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    return float("-inf")


def encode(wav: Path, mp3: Path, chapter: dict[str, object], index: int) -> None:
    title = f"{chapter['article_id']} · {chapter['english_title']}"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
            "-codec:a", "libmp3lame", "-q:a", "4", "-ac", "1", "-ar", "22050",
            "-metadata", f"title={title}",
            "-metadata", "album=CET-4 Vocabulary Stories",
            "-metadata", "artist=CET-4 Vocabulary Stories",
            "-metadata", f"track={index}/{TOTAL_CHAPTERS}",
            "-metadata", "genre=Speech",
            str(mp3),
        ],
        check=True,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", default="", help="CH001-CH005 or CH001,CH002")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv[1:])

    out_dir = Path(args.out)
    chapters = load_chapters()
    if len(chapters) != TOTAL_CHAPTERS:
        print(f"WARNING: found {len(chapters)} chapters, expected {TOTAL_CHAPTERS}")

    if args.chapters:
        wanted: set[str] = set()
        for part in args.chapters.split(","):
            part = part.strip()
            if "-" in part:
                low, high = part.split("-", 1)
                wanted.update(
                    f"CH{n:03d}" for n in range(int(low[2:]), int(high[2:]) + 1)
                )
            else:
                wanted.add(part)
        chapters = [c for c in chapters if str(c["article_id"]) in wanted]

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} is required and was not found on PATH")

    print(f"chapters   : {len(chapters)}")
    print(f"voice      : {args.voice}   rate {args.rate}")
    print(f"output     : {out_dir}")

    records: list[dict[str, object]] = []
    if not args.verify_only:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            jobs: list[tuple[Path, Path, str, int]] = []
            for index, chapter in enumerate(chapters, start=1):
                chapter_id = str(chapter["article_id"])
                ssml = tmpdir / f"{chapter_id}.ssml"
                ssml.write_text(ssml_for(chapter, args.voice, args.rate), encoding="utf-8")
                jobs.append((ssml, tmpdir / f"{chapter_id}.wav", args.voice, args.rate))
            synthesize(jobs)
            print(f"  encoding   : {len(jobs)} chapters to MP3")
            for index, (chapter, (_ssml, wav, _v, _r)) in enumerate(
                zip(chapters, jobs), start=1
            ):
                chapter_id = str(chapter["article_id"])
                mp3 = out_dir / f"{chapter_id}.mp3"
                encode(wav, mp3, chapter, index)
                if index % 25 == 0 or index == len(chapters):
                    print(f"    {index}/{len(chapters)}")

    print("verifying  :")
    problems: list[str] = []
    for index, chapter in enumerate(chapters, start=1):
        chapter_id = str(chapter["article_id"])
        mp3 = out_dir / f"{chapter_id}.mp3"
        if not mp3.is_file():
            problems.append(f"{chapter_id}: missing {mp3.name}")
            continue
        words = sum(len(str(p).split()) for p in chapter["english_paragraphs"])  # type: ignore[index]
        duration = probe_duration(mp3)
        wpm = words / duration * 60 if duration else 0.0
        volume = mean_volume_db(mp3, max(0.0, duration / 2 - 7.5))
        record = {
            "chapter_id": chapter_id,
            "title": chapter["english_title"],
            "words": words,
            "seconds": round(duration, 2),
            "words_per_minute": round(wpm, 1),
            "bytes": mp3.stat().st_size,
            "sha256": hashlib.sha256(mp3.read_bytes()).hexdigest(),
            "mid_slice_mean_db": round(volume, 1),
        }
        records.append(record)
        if not MIN_WPM <= wpm <= MAX_WPM:
            problems.append(
                f"{chapter_id}: {wpm:.0f} wpm is outside {MIN_WPM}-{MAX_WPM} "
                f"({duration:.0f}s for {words} words) - likely truncated"
            )
        if volume < -50:
            problems.append(f"{chapter_id}: mid-file mean volume {volume:.1f} dB (silence?)")

    if records:
        total_seconds = sum(float(r["seconds"]) for r in records)
        total_bytes = sum(int(r["bytes"]) for r in records)
        print(f"  chapters verified : {len(records)}")
        print(f"  total duration    : {total_seconds/3600:.2f} h ({total_seconds/60:.0f} min)")
        print(f"  total size        : {total_bytes/1024/1024:.1f} MB")
        print(f"  wpm min/median/max: "
              f"{min(r['words_per_minute'] for r in records):.0f} / "
              f"{sorted(r['words_per_minute'] for r in records)[len(records)//2]:.0f} / "
              f"{max(r['words_per_minute'] for r in records):.0f}")
        MANIFEST.write_text(
            json.dumps(
                {
                    "voice": args.voice,
                    "rate": args.rate,
                    "paragraph_pause_ms": PARAGRAPH_PAUSE_MS,
                    "chapters": records,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"  manifest          : {MANIFEST.relative_to(ROOT)}")

    if problems:
        print(f"PROBLEMS ({len(problems)}):")
        for problem in problems[:30]:
            print("  -", problem)
        return 1
    print("  all chapters verified: present, plausible duration, not silent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
