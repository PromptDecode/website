#!/usr/bin/env node
/**
 * Runs the shared test vectors against the browser decoder, without a browser.
 * Zero dependencies; run from anywhere:
 *
 *     node tools/vectors.mjs            # checks the repository this file is in
 *     node tools/vectors.mjs <root>     # checks another checkout (deploy.sh does this)
 *
 * The page's central claim is that the decoder finds exactly the classes it
 * names and nothing else. Prose cannot prove that, and neither can the site's
 * own demo, so tools/core/vectors.json pins the corner cases as data: the two
 * no-op ends of the tag block, the twelve bidi controls, both variation
 * selector ranges, the near misses that must stay visible, and the sample
 * payload the page itself ships. When promptdecode-core publishes its copy of
 * the same file, this runner is what proves the engine and the browser build
 * agree on every one of them instead of being assumed to.
 *
 * The decoder is not copied into this file. The region between the
 * `@decoder start` and `@decoder end` marker lines in assets/promptdecode.js
 * is sliced out and evaluated as-is, so the vectors run against the very
 * source the browser runs and a refactor that changes behaviour fails here
 * before it ships. A missing marker is a failure, not a skip: running nothing
 * and calling it green is the one result a checker must never produce.
 *
 * Every string this file prints is escaped where it would otherwise be
 * invisible. A test suite about hidden characters that hides its own failures
 * would be exactly the joke this project exists to catch.
 *
 * Exit status is 0 when every vector passes, 1 when any fails or the setup is
 * broken (a file missing, the JSON malformed, a marker gone).
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Same root idiom as check.py: an optional argument for deploy.sh, otherwise
// the directory this script's directory lives in, which is the repository root.
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(process.argv[2] || path.dirname(here));

const fail = (msg) => {
  console.log(msg);
  process.exit(1);
};

const vectorsPath = path.join(root, "tools/core/vectors.json");
const decoderPath = path.join(root, "assets/promptdecode.js");

if (!existsSync(vectorsPath)) fail(`tools/core/vectors.json: not found under ${root}; there is nothing to run`);
if (!existsSync(decoderPath)) fail(`assets/promptdecode.js: not found under ${root}; there is nothing to run it against`);

let vectors;
try {
  vectors = JSON.parse(readFileSync(vectorsPath, "utf8"));
} catch (err) {
  fail(`tools/core/vectors.json: does not parse: ${err.message}`);
}
if (!vectors || !Array.isArray(vectors.vectors)) {
  fail('tools/core/vectors.json: does not have a "vectors" array; the file is not the shape the runner agrees to run');
}

// ---------------------------------------------------------- the real decoder
const START = "/* @decoder start */";
const END = "/* @decoder end */";
const lines = readFileSync(decoderPath, "utf8").split("\n");
const startAt = lines.findIndex((l) => l.trim() === START);
const endAt = lines.findIndex((l) => l.trim() === END);
if (startAt === -1 || endAt === -1 || endAt <= startAt) {
  fail(`assets/promptdecode.js: the "${START}" and "${END}" marker lines are missing or out of order; ` +
    "the runner must slice the decoder out of the real source, so a copy will not do");
}

let decodeText;
try {
  decodeText = new Function(lines.slice(startAt + 1, endAt).join("\n") + "\nreturn decodeText;")();
} catch (err) {
  fail(`assets/promptdecode.js: the decoder region does not evaluate: ${err.message}`);
}
if (typeof decodeText !== "function") {
  fail("assets/promptdecode.js: the decoder region does not define decodeText; nothing can be checked");
}

// ------------------------------------------------------------------ output
// Escape anything a terminal would render as nothing (or as the wrong thing).
const NAMED = { "\n": "\\n", "\r": "\\r", "\t": "\\t" };
function show(s) {
  let out = "";
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (NAMED[ch]) out += NAMED[ch];
    else if (cp < 0x20 || cp > 0x7e) {
      out += cp > 0xffff
        ? `\\u{${cp.toString(16).toUpperCase()}}`
        : `\\u${cp.toString(16).toUpperCase().padStart(4, "0")}`;
    } else out += ch;
  }
  return `"${out}"`;
}

// What a reader still sees: every part of every visible segment, in order.
function visibleOf(result) {
  return result.segs.filter((s) => !s.hidden).map((s) => s.parts.join("")).join("");
}

// --------------------------------------------------------------- the vectors
let failed = 0;
const total = vectors.vectors.length;

for (const [i, v] of vectors.vectors.entries()) {
  for (const field of ["name", "input", "expect"]) {
    if (v[field] === undefined) {
      fail(`tools/core/vectors.json: vector #${i + 1} has no "${field}"; the file is not the shape the runner agrees to run`);
    }
  }
  for (const field of ["counts", "total", "payload", "visible"]) {
    if (v.expect[field] === undefined) {
      fail(`tools/core/vectors.json: vector "${v.name}" expects no "${field}"; every vector pins all four`);
    }
  }

  const got = decodeText(v.input);
  const diffs = [];
  for (const bucket of ["tag", "bidi", "vs"]) {
    if (got.counts[bucket] !== v.expect.counts[bucket]) {
      diffs.push(`    counts.${bucket}: expected ${v.expect.counts[bucket]}, got ${got.counts[bucket]}`);
    }
  }
  if (got.total !== v.expect.total) diffs.push(`    total: expected ${v.expect.total}, got ${got.total}`);
  if (got.payload !== v.expect.payload) diffs.push(`    payload: expected ${show(v.expect.payload)}, got ${show(got.payload)}`);
  const visible = visibleOf(got);
  if (visible !== v.expect.visible) diffs.push(`    visible: expected ${show(v.expect.visible)}, got ${show(visible)}`);

  if (diffs.length) {
    failed++;
    console.log(`FAIL ${v.name}`);
    for (const d of diffs) console.log(d);
  }
}

if (failed) console.log(`vectors: ${failed} of ${total} failed`);
else console.log(`vectors: ${total} ok`);
process.exit(failed ? 1 : 0);
