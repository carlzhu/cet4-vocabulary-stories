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
  window: {
    devicePixelRatio: 1,
    innerWidth: 1024,
    innerHeight: 768,
    addEventListener: noop,
    location: { hash: "" },
    localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
  },
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
check("every word has a short gloss for the line under it",
  DATA.words.every((w) => typeof w.s === "string" && w.s.length > 0));
check("short glosses are short enough to read at a glance",
  DATA.words.every((w) => w.s.length <= 15),
  String(Math.max(...DATA.words.map((w) => w.s.length))));
check("short glosses keep no list separator",
  DATA.words.every((w) => !/[,，;；、]/.test(w.s)));
check("every word carries a key flag", DATA.words.every((w) => w.k === 0 || w.k === 1));
check("chapters are 1..137",
  DATA.chapters.every((c, i) => c.n === i + 1), DATA.chapters.map((c) => c.n).join(",").slice(0, 40));
const perChapter = new Map();
for (const w of DATA.words) perChapter.set(w.c, (perChapter.get(w.c) || 0) + 1);
check("every chapter has words", perChapter.size === 137 && [...perChapter.values()].every((n) => n > 0));

/* key words: the rule the page documents must hold on every single entry */
const keyByRule = (w) => w.w.length >= 9 || (w.w.length >= 7 && w.k === 1);
check("no key word is shorter than 7 letters",
  DATA.words.every((w) => !w.k || w.w.length >= 7),
  String(Math.min(...DATA.words.filter((w) => w.k).map((w) => w.w.length))));
check("every word of 9+ letters is flagged key",
  DATA.words.every((w) => w.w.length < 9 || w.k === 1));
check("declared key total matches the flags",
  DATA.key_total === DATA.words.filter((w) => w.k).length, String(DATA.key_total));
const keyPerChapter = new Map();
for (const w of DATA.words) if (w.k) keyPerChapter.set(w.c, (keyPerChapter.get(w.c) || 0) + 1);
check("per-chapter key counts published in chapters[]",
  DATA.chapters.every((c) => (keyPerChapter.get(c.n) || 0) === c.kn));
check("every chapter has at least one key word",
  DATA.chapters.every((c) => c.kn >= 1),
  `min ${Math.min(...DATA.chapters.map((c) => c.kn))}`);
check("the top-up floor is reachable in every chapter",
  DATA.chapters.every((c) => (perChapter.get(c.n) || 0) >= DATA.key_floor),
  `floor ${DATA.key_floor}`);
void keyByRule;

/* poolFor: the scope rules the setup screen offers */
const floor = DATA.key_floor;
for (const chapter of DATA.chapters) {
  const keyPool = Core.poolFor(DATA.words, "key", chapter.n, chapter.a, floor);
  const whole = Core.poolFor(DATA.words, "chapter", chapter.n, chapter.a, floor);
  if (keyPool.length < Math.min(floor, whole.length)) {
    check(`CH${chapter.n} key pool reaches the floor`, false, String(keyPool.length));
  }
  if (!keyPool.every((w) => w.c === chapter.n)) {
    check(`CH${chapter.n} key pool stays in the chapter`, false);
  }
  if (whole.length !== (perChapter.get(chapter.n) || 0)) {
    check(`CH${chapter.n} full pool is the whole chapter`, false, `${whole.length}`);
  }
}
check("every chapter's key pool is playable", true);

check("key scope returns only key words when there are enough",
  (() => {
    const chapter = DATA.chapters.find((c) => c.kn >= floor);
    return Core.poolFor(DATA.words, "key", chapter.n, chapter.a, floor).every((w) => w.k === 1);
  })());

check("chapter scope is ordered key words first",
  (() => {
    const chapter = DATA.chapters.find((c) => c.kn >= 3 && c.kn < 40);
    const pool = Core.poolFor(DATA.words, "chapter", chapter.n, chapter.a, floor);
    const firstPlain = pool.findIndex((w) => !w.k);
    return firstPlain === -1 || pool.slice(firstPlain).every((w) => !w.k);
  })());

check("arc scope stays in the arc",
  Core.poolFor(DATA.words, "arc", 1, 4, floor).every((w) => w.a === 4));
check("arc scope is not empty", Core.poolFor(DATA.words, "arc", 1, 4, floor).length > 0);
check("all scope returns everything",
  Core.poolFor(DATA.words, "all", 1, 1, floor).length === DATA.words.length);
check("the top-up is used when a chapter is thin",
  (() => {
    const thin = DATA.chapters.filter((c) => c.kn < floor);
    if (!thin.length) return true;  // no thin chapters: the rule cannot be exercised
    const pool = Core.poolFor(DATA.words, "key", thin[0].n, thin[0].a, floor);
    return pool.length >= floor && pool.every((w) => w.c === thin[0].n);
  })());

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
