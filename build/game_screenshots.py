"""Capture the typing game's four UI states as screenshots, using headless Edge/Chrome.

This is how ``build/qa/game-*.png`` were produced. It exists because the game's logic
can be tested in Node but its **rendering cannot** - and a single-file page that renders
wrongly is a broken deliverable. A headless screenshot turns "the layout should be
fine" into something that was actually looked at.

Two things this works around:

* **Virtual time barely drives requestAnimationFrame.** With ``--virtual-time-budget``
  the game's loop ran twice in the entire window, so its spawn timer never fired and the
  board was empty - which looks like a rendering bug and is not one. Each probe therefore
  stages the state it wants drawn and calls the same ``draw()`` the running game uses,
  instead of waiting for the animation.
* **The probe must not be rewritten by PowerShell.** ``Get-Content -Raw | Set-Content
  -Encoding UTF8`` double-encodes a BOM-less UTF-8 file and turns every Chinese label
  into mojibake, which also looks like a bug in the page. The probes are written here,
  in Python, as UTF-8.

Usage:
    python build/game_screenshots.py                       # auto-detect the browser
    python build/game_screenshots.py --browser "C:/path/to/msedge.exe"
    python build/game_screenshots.py --out build/qa
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "CET4_Typing_Game.html"
DEFAULT_OUT = ROOT / "build" / "qa"

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# Each probe stages one state and draws it. They are appended before </body>, where the
# page's own top-level const bindings (state, WORDS, CHAPTERS, Core, draw, updateHud,
# finish, renderSetup, chapterOf) are already in scope, because classic scripts share the
# global lexical environment.
PROBES = {
    "game-start": """
  state.chapter = 68;
  state.arc = chapterOf(68).a;
  state.scope = "key";
  renderSetup();
""",
    "game-play": """
  state.chapter = 68;
  state.arc = chapterOf(68).a;
  state.scope = "key";
  renderSetup();
  document.getElementById("btn-start").click();
  var keys = Core.poolFor(WORDS, "key", state.chapter, state.arc, DATA.key_floor);
  state.falling = keys.slice(0, 5).map(function (entry, position) {
    return { text: entry.w, phonetic: entry.p, meaning: entry.m, key: entry.k,
             x: 80 + position * 215, y: 62 + (position % 3) * 126, speed: 33, dead: false };
  });
  var active = state.falling[2];
  state.buffer = active.text.slice(0, Math.max(1, Math.ceil(active.text.length / 3)));
  state.active = active;
  state.score = 246; state.combo = 7; state.cleared = 6; state.level = 1;
  state.keyCleared = 4; state.lives = 2; state.keystrokes = 96; state.goodKeystrokes = 92;
  updateHud(true); draw();
""",
    "game-over": """
  state.chapter = 68;
  state.arc = chapterOf(68).a;
  state.scope = "key";
  renderSetup();
  document.getElementById("btn-start").click();
  state.score = 1830; state.cleared = 16; state.keyCleared = 13; state.bestCombo = 12;
  state.level = 2; state.lives = 0; state.keystrokes = 402; state.goodKeystrokes = 378;
  state.review = Core.poolFor(WORDS, "key", 68, state.arc, DATA.key_floor)
    .slice(0, 7).map(function (entry) {
      return { text: entry.w, meaning: entry.m };
    });
  finish();
""",
    "game-arc": """
  state.arc = 9;
  state.chapter = CHAPTERS.filter(function (c) { return c.a === 9; })[0].n;
  state.scope = "chapter";
  renderSetup();
""",
}


def find_browser(explicit: str | None) -> str:
    if explicit:
        return explicit
    for candidate in BROWSERS:
        if pathlib.Path(candidate).is_file():
            return candidate
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("no Edge or Chrome found; pass --browser")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--size", default="1280,820")
    args = parser.parse_args(argv[1:])

    browser = find_browser(args.browser)
    if not PAGE.is_file():
        raise SystemExit(f"{PAGE.name} has not been generated; run make_typing_game.py")
    page = PAGE.read_text(encoding="utf-8")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"  browser : {browser}")

    with tempfile.TemporaryDirectory() as work:
        work_path = pathlib.Path(work)
        for name, body in PROBES.items():
            probe = work_path / f"{name}.html"
            script = f"<script>\n(function () {{\n{body}\n}})();\n</script>\n</body>" if body else "</body>"
            probe.write_text(page.replace("</body>", script, 1), encoding="utf-8")
            shot = out / f"{name}.png"
            result = subprocess.run(
                [
                    browser, "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={work_path / 'profile'}",
                    f"--window-size={args.size}",
                    f"--screenshot={shot}",
                    probe.as_uri(),
                ],
                capture_output=True,
                text=True,
            )
            if not shot.is_file():
                print(f"  FAILED {name}: {result.stderr.strip()[-200:]}")
                return 1
            print(f"  {name}.png  {shot.stat().st_size:,} B")

    print(f"  wrote {len(PROBES)} screenshots to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
