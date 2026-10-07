/* Smoke-test the typing game's logic without a browser.
 *
 * The game lives inside a single HTML file, so there is no module to import. This
 * extracts the game <script> from the generated page, runs it in a VM with a minimal
 * DOM stub, and drives the pure `Core` object directly. That covers the parts a static
 * check cannot: which word a keystroke resolves to, when a word is completed, what a
 * wrong letter does, and how difficulty scales.
 *
 * What it cannot cover is rendering and real keyboard events; those need a browser.
 *
 * Usage: node build/typing_game_smoke.mjs [path-to-html]
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const htmlPath = process.argv[2] || resolve(here, "..", "CET4_Typing_Game.html");
const html = readFileSync(htmlPath, "utf8");

/* ---------- extract the data and the game script ---------- */
const dataMatch = html.match(
  /<script id="word-data" type="application\/json">([\s\S]*?)<\/script>/
);
if (!dataMatch) throw new Error("no embedded word-data block found");
const DATA = JSON.parse(dataMatch[1]);

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
if (!scripts.length) throw new Error("no game script found");
const gameSource = scripts[scripts.length - 1][1];

/* ---------- minimal DOM ---------- */
const noop = () => {};
const ctxStub = new Proxy(
  {
    measureText: (text) => ({ width: String(text).length * 14 }),
    setTransform: noop,
  },
  {
    get(target, prop) {
      if (prop in target) return target[prop];
      return noop; // every drawing call is fine to ignore
    },
    set(target, prop, value) {
      target[prop] = value;
      return true;
    },
  }
);

const elements = new Map();
function makeElement(id) {
  return {
    id,
    textContent: id === "word-data" ? dataMatch[1] : "",
    innerHTML: "",
    value: "1",
    dataset: {},
    style: {},
    clientWidth: 1024,
    clientHeight: 768,
    width: 0,
    height: 0,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    appendChild: noop,
    append: noop,
    querySelectorAll: () => [],
    addEventListener: noop,
    closest: () => null,
    getContext: () => ctxStub,
  };
}

const sandbox = {
  console,
  Math,
  Date,
  JSON,
  Number,
  String,
  Boolean,
  Array,
  Object,
  Set,
  performance: { now: () => Date.now() },
  requestAnimationFrame: noop,
  alert: () => {
    throw new Error("the game called alert() during startup");
  },
  window: { devicePixelRatio: 1, innerWidth: 1024, innerHeight: 768, addEventListener: noop },
  document: {
    getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, makeElement(id));
      return elements.get(id);
    },
    createElement: () => makeElement("created"),
  },
};
sandbox.globalThis = sandbox;

vm.runInNewContext(`${gameSource}\n;globalThis.__Core = Core;`, sandbox, {
  filename: "typing-game.js",
});
const Core = sandbox.__Core;
if (!Core) throw new Error("the script did not expose Core");

/* ---------- assertions ---------- */
let checks = 0;
const failures = [];
function check(name, condition, detail = "") {
  checks += 1;
  if (!condition) failures.push(`${name}${detail ? " :: " + detail : ""}`);
}
const word = (text, y, dead = false) => ({ text, y, dead, phonetic: "", meaning: "" });

/* data */
check("embedded word count", DATA.words.length === 6127, String(DATA.words.length));
check("chapter count", DATA.chapters.length === 137, String(DATA.chapters.length));
check("every word has a chapter and arc",
  DATA.words.every((w) => Number.isInteger(w.c) && w.c >= 1 && w.c <= 137 && Number.isInteger(w.a)));
check("every word has a gloss", DATA.words.every((w) => typeof w.m === "string" && w.m.length > 0));
check("chapters are 1..137",
  DATA.chapters.every((c, i) => c.n === i + 1), DATA.chapters.map((c) => c.n).join(",").slice(0, 40));
const perChapter = new Map();
for (const w of DATA.words) perChapter.set(w.c, (perChapter.get(w.c) || 0) + 1);
check("every chapter has words", perChapter.size === 137 && [...perChapter.values()].every((n) => n > 0));

/* level curve */
check("levelFor starts at 1", Core.levelFor(0) === 1 && Core.levelFor(9) === 1);
check("levelFor steps every 10", Core.levelFor(10) === 2 && Core.levelFor(25) === 3);
check("spawn interval shrinks", Core.spawnFor(1) > Core.spawnFor(5));
check("spawn interval has a floor", Core.spawnFor(50) === 0.8, String(Core.spawnFor(50)));
check("speed rises with level", Core.speedFor(2, 1) > Core.speedFor(1, 1));
check("difficulty scales speed", Core.speedFor(1, 1.6) > Core.speedFor(1, 1));
check("score grows with combo", Core.scoreFor("able", 5) > Core.scoreFor("able", 0));

/* matching: the lowest word wins, because it is the one about to hit the floor */
check("match finds a prefix", Core.match([word("about", 10)], "ab")?.text === "about");
check("match is case-insensitive", Core.match([word("About", 10)], "ab")?.text === "About");
check("match ignores dead words", Core.match([word("about", 10, true)], "ab") === null);
check("match returns null with no candidate", Core.match([word("about", 10)], "zz") === null);
check("match prefers the lowest word",
  Core.match([word("about", 10), word("above", 300)], "ab")?.text === "above");

/* keystrokes */
let r = Core.keystroke([word("able", 100)], "", "a");
check("first letter starts a buffer", r.buffer === "a" && r.matches !== null && !r.restarted);
r = Core.keystroke([word("able", 100)], "a", "b");
check("second letter extends", r.buffer === "ab" && r.matches !== null);
r = Core.keystroke([word("able", 100)], "abl", "e");
check("last letter completes the word", r.buffer === "able" && r.matches?.text === "able");
r = Core.keystroke([word("able", 100)], "", "z");
check("wrong letter yields no match", r.buffer === "" && r.matches === null && !r.restarted);
r = Core.keystroke([word("able", 100), word("zebra", 50)], "ab", "z");
check("stale buffer restarts from the new letter",
  r.buffer === "z" && r.matches?.text === "zebra" && r.restarted === true);

/* a word that is split across two candidates resolves to the right one */
r = Core.keystroke([word("car", 10), word("carpet", 200)], "car", "p");
check("overlapping words continue the longer one", r.matches?.text === "carpet" && r.buffer === "carp");

/* multi-word entries are typeable with a space. 14 lemmas are phrases such as
   "ice cream"; the page has to accept the space for them or they can never be typed. */
const phrase = word("ice cream", 100);
check("a space continues a phrase", Core.keystroke([phrase], "ice", " ").buffer === "ice ");
r = Core.keystroke([phrase], "ice ", "c");
check("a phrase can be completed", r.matches?.text === "ice cream");
let phraseBuffer = "";
for (const char of "ice cream") phraseBuffer = Core.keystroke([phrase], phraseBuffer, char).buffer;
check("typing every character of a phrase completes it",
  phraseBuffer === "ice cream", phraseBuffer);

/* shuffle keeps the multiset */
const source = DATA.words.slice(0, 50).map((w) => w.w);
const shuffled = Core.shuffle(source);
check("shuffle preserves length", shuffled.length === source.length);
check("shuffle preserves elements",
  [...shuffled].sort().join("|") === [...source].sort().join("|"));

/* a full simulated round: every pool word should complete when its last letter is typed */
const pool = DATA.words.slice(0, 25).map((w) => ({ ...word(w.w, 1000), meaning: w.m }));
let completed = 0;
for (const entry of pool) {
  let buffer = "";
  for (const char of entry.text) {
    const result = Core.keystroke([entry], buffer, char);
    buffer = result.buffer;
    if (buffer.length === entry.text.length) completed += 1;
  }
}
check("every pool word completes when fully typed", completed === pool.length,
  `${completed}/${pool.length}`);

/* ---------- report ---------- */
if (failures.length) {
  console.error(`FAILED ${failures.length} of ${checks} checks:`);
  for (const failure of failures) console.error("  - " + failure);
  process.exit(1);
}
console.log(`  ${checks} logic checks passed against ${htmlPath}`);
console.log(`  embedded: ${DATA.words.length} words, ${DATA.chapters.length} chapters`);
