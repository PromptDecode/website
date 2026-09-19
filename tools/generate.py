#!/usr/bin/env python3
"""Regenerates every generated region on the site from the class data in tools/core/.

    python3 tools/generate.py                 # rewrite the generated regions in place
    python3 tools/generate.py --check         # write nothing; print a diff; exit 1 on drift
    python3 tools/generate.py --emit rust     # print a Rust const table for the engine repo, once it exists

All three accept an optional root argument (deploy.sh style, like check.py):
`python3 tools/generate.py <root> ...` operates on another checkout. The root
defaults to the directory this script's directory lives in, which is the
repository root.

The list of Unicode classes the decoder implements is the site's central
claim, and it is spelled out in three places at once: the constants in
`assets/promptdecode.js`, the table in README.md and the list in `llms.txt`.
Hand-keeping three spellings of one list is exactly how the claim drifts, so
the single source is `tools/core/classes.json`, kept under `tools/core/`
until promptdecode-core publishes a release to pin (see
`tools/core/pin.json`). This script rewrites the other three from it, and
check.py runs it in --check mode and fails on any difference, in either
direction.

`classes.json` holds only the mechanical claim: class identity and code point
ranges. The wording around each class is website prose, not engine data, so
it lives here in KNOWN, copied from what README.md and llms.txt say today.
A class that shows up in classes.json without an entry in KNOWN is a loud
failure, not a constant nothing reads and not a table row with an empty cell.

Module API, for tools/check.py to import rather than shell out to:

  load_classes(root)
      Parses `<root>/tools/core/classes.json`. Returns a list of dicts with
      keys "id" and "name" (strings) and "ranges", a list of (from, to)
      int tuples, inclusive on both ends, in file order. Raises ClassesError
      if the file is missing, malformed, or names a class id this module does
      not know (the same failure the CLI would raise: fix the data or the
      prose table before regenerating).

  targets(root, classes)
      Returns one (relpath, current_text, wanted_text) tuple per generated
      region, for "assets/promptdecode.js", "README.md" and "llms.txt", in
      that order. Both texts are whole file contents; wanted_text is byte for
      byte what `--check`-clean output would be, so a caller can diff the pair
      directly (difflib.unified_diff on splitlines(keepends=True) reads well)
      or write wanted_text back out. Raises ClassesError if a file is missing
      a marker region.

  rust_tables(classes)
      Returns the Rust const table (a `&[(u32, u32)]` per class, inclusive
      pairs, matching classes.json) as a string with a trailing newline. This
      output has no consumer in this repository; it is printed by --emit rust
      for an engine repo to paste or consume, when one exists.

  ClassesError
      The exception everything raises. Its message is written to be printed
      to a human verbatim.

Stdlib only, like check.py: this runs in CI and in deploy.sh with whatever
python3 the machine happens to have.
"""

import argparse
import difflib
import json
import pathlib
import re
import sys
import textwrap

CLASSES_PATH = "tools/core/classes.json"
JS_PATH = "assets/promptdecode.js"
README_PATH = "README.md"
LLMS_PATH = "llms.txt"

# llms.txt is hard wrapped by hand; 79 is the width the rest of the file is
# wrapped to, so the generated region wraps identically.
LLMS_WIDTH = 79

# Markers are matched against a stripped whole line, so the indentation is the
# emitter's business and the human's freedom.
JS_BEGIN = "/* @generated classes */"
JS_END = "/* @generated end */"
MD_BEGIN = "<!-- @generated classes -->"
MD_END = "<!-- @generated end -->"

# Counts are spelled as words in the prose. The llms.txt lede spells up to
# ten and falls back to digits above that; the bidi bullet's existing wording
# spells "twelve", so it keeps spelling up to twenty.
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
         "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]

# The website's wording per class, keyed by class id. `why` is the README
# table's third cell, verbatim; `llms` is the llms.txt bullet as a format
# string over {ranges} (the class's ranges, e.g. "U+E0000 to U+E007F"),
# {points} (every code point listed one by one) and {count} (the number of
# code points, spelled out); `llms_join` is how multiple ranges read in that
# bullet ("and" for the variation selectors, where the sentence is prose);
# `readme_name` is the README's first cell, which may abbreviate where the
# class data spells out ("Bidi" against "Bidirectional").
KNOWN = {
    "tag": {
        "readme_name": "Unicode tag block",
        "why": "Mirrors printable ASCII at an offset of `0xE0000`, so a run of "
               "them carries recoverable text. The decoder reconstructs it",
        "llms": "Unicode tag block, {ranges}. These mirror printable ASCII at "
                "an offset of 0xE0000, so a run of them is recoverable as "
                "plain text.",
        "llms_join": ", ",
    },
    "bidi": {
        "readme_name": "Bidi controls and overrides",
        "why": "Reorders rendered text without changing the bytes a parser or "
               "a model sees",
        "llms": "Bidirectional controls and overrides, {count} code points, "
                "listed in full because a range would hide which of them are "
                "actually read: {points}.",
        "llms_join": ", ",
    },
    "vs": {
        "readme_name": "Variation selectors",
        "why": "Carry data with no visible glyph of their own",
        "llms": "Variation selectors: {ranges}.",
        "llms_join": ", and ",
    },
}


class ClassesError(Exception):
    """A problem a human has to fix, in the data or in the prose table."""


def _unknown(cid):
    return ClassesError(
        "tools/core/classes.json defines class '%s', which tools/generate.py "
        "does not know. Before regenerating, teach the decoder to detect it "
        "in assets/promptdecode.js, and write its README table cell and "
        "llms.txt bullet into KNOWN in tools/generate.py. A generated "
        "constant nothing reads, or a table row with an empty cell, is the "
        "one failure this project cannot survive." % cid)


def hx(cp):
    """A code point as a JS/Rust hex literal: uppercase, at least 4 digits."""
    return "0x%04X" % cp


def u(cp):
    """A code point as the U+ spelling a reader checks the promise against."""
    return "U+%04X" % cp


def count_words(n, through=10):
    """The number n as prose: a word up to `through`, digits past it."""
    if 0 <= n <= through:
        return WORDS[n]
    return str(n)


def code_points(cls):
    """Every code point the class covers, expanded, in range order."""
    out = []
    for lo, hi in cls["ranges"]:
        out.extend(range(lo, hi + 1))
    return out


def contiguous_runs(cls, min_run):
    """A class's code points grouped into maximal consecutive runs.

    Runs shorter than min_run are split back into single code points, because
    the README spells a pair (U+200E, U+200F) but compresses a run of three
    or more (U+202A to U+202E). That split is the spelling the table has
    always used, and the generated cell has to match it byte for byte.
    """
    runs = []
    for cp in code_points(cls):
        if runs and cp == runs[-1][1] + 1:
            runs[-1][1] = cp
        else:
            runs.append([cp, cp])
    out = []
    for lo, hi in runs:
        if hi - lo + 1 < min_run:
            out.extend((c, c) for c in range(lo, hi + 1))
        else:
            out.append((lo, hi))
    return out


def _span(lo, hi):
    """One run as prose: a single U+ spelling, or a `to` span."""
    if lo == hi:
        return u(lo)
    return "%s to %s" % (u(lo), u(hi))


def readme_span(lo, hi):
    """One run as the README spells it: each code point backticked on its
    own, a run joined by `to` outside the backticks. The table has always
    read `U+E0000` to `U+E007F`, never one span inside one pair."""
    if lo == hi:
        return "`%s`" % u(lo)
    return "`%s` to `%s`" % (u(lo), u(hi))


def readme_ranges(cls):
    """The README Range cell: every code point backticked, runs compressed."""
    return ", ".join(readme_span(lo, hi) for lo, hi in contiguous_runs(cls, min_run=3))


def llms_bullet(cls):
    """One llms.txt sub-bullet, unwrapped; the caller does the wrapping."""
    spec = KNOWN[cls["id"]]
    if "{points}" in spec["llms"]:
        # The bidi bullet lists every code point in full, because a range
        # would hide which of them the decoder actually reads.
        return spec["llms"].format(
            count=count_words(len(code_points(cls)), through=20),
            points=", ".join(u(cp) for cp in code_points(cls)))
    return spec["llms"].format(
        ranges=spec["llms_join"].join(_span(lo, hi) for lo, hi in cls["ranges"]))


# --------------------------------------------------------------- JS emitter
# The decoder knows these three shapes and no others: the tag block as two
# named bounds (its decode is arithmetic on the offset), bidi as a flat list
# of single code points (membership, not ranges), and the variation selectors
# as inclusive pairs. Anything else needs a decoder change first.

def js_lines(cls):
    cid = cls["id"]
    if cid == "tag":
        if len(cls["ranges"]) != 1:
            raise ClassesError(
                "class 'tag' is emitted as TAG_START and TAG_END, so it must "
                "be exactly one range in tools/core/classes.json")
        lo, hi = cls["ranges"][0]
        return ["var TAG_START = %s, TAG_END = %s;" % (hx(lo), hx(hi))]
    if cid == "bidi":
        for lo, hi in cls["ranges"]:
            if lo != hi:
                raise ClassesError(
                    "class 'bidi' is emitted as single code points; a range "
                    "of more than one needs the decoder to read ranges first")
        return ["var BIDI = [%s];" % ", ".join(hx(lo) for lo, _ in cls["ranges"])]
    if cid == "vs":
        pairs = ", ".join("[%s, %s]" % (hx(lo), hx(hi)) for lo, hi in cls["ranges"])
        return ["var VS = [%s];" % pairs]
    raise _unknown(cid)


def js_block(classes):
    lines = [
        "  " + JS_BEGIN,
        "  /* Generated by tools/generate.py from tools/core/classes.json. Do not",
        "     edit by hand: tools/check.py fails on any difference, because the",
        "     list is the claim. Regenerate with python3 tools/generate.py. */",
    ]
    for cls in classes:
        lines.extend("  " + line for line in js_lines(cls))
    lines.append("  " + JS_END)
    return "\n".join(lines)


# ------------------------------------------------------------ prose emitters

def readme_block(classes):
    lines = [MD_BEGIN,
             "| Class | Range | Why it matters |",
             "| :--- | :--- | :--- |"]
    for cls in classes:
        spec = KNOWN[cls["id"]]
        lines.append("| %s | %s | %s |" % (spec["readme_name"], readme_ranges(cls), spec["why"]))
    lines.append(MD_END)
    return "\n".join(lines)


def llms_block(classes):
    # The count in the lede is derived, so adding a class rewords the
    # sentence instead of leaving it lying.
    lede = "- The %s classes it reads, which are the whole of its claim:" % count_words(len(classes))
    lines = [MD_BEGIN, lede]
    for cls in classes:
        bullet = llms_bullet(cls)
        wrapped = textwrap.fill(
            bullet, width=LLMS_WIDTH,
            initial_indent="  - ", subsequent_indent="    ",
            # U+200E and friends are tokens, not prose: never split them.
            break_long_words=False, break_on_hyphens=False)
        lines.extend(wrapped.split("\n"))
    lines.append(MD_END)
    return "\n".join(lines)


# ------------------------------------------------------------- Rust emitter

def rust_tables(classes):
    """The engine repo's const table. Nothing in this repository consumes it."""
    lines = [
        "// Class tables for the promptdecode decoder.",
        "//",
        "// Generated by tools/generate.py in PromptDecode/website from",
        "// tools/core/classes.json, the copy promptdecode-core is expected to",
        "// publish; the intended pin is recorded in tools/core/pin.json. The",
        "// website has no Rust and consumes none of this; it is printed by:",
        "//",
        "//     python3 tools/generate.py --emit rust",
        "",
    ]
    for cls in classes:
        pairs = ["(%s, %s)" % (hx(lo), hx(hi)) for lo, hi in cls["ranges"]]
        name = cls["id"].upper() + "_RANGES"
        lines.append("/// %s." % cls["name"])
        if len(pairs) <= 4:
            lines.append("pub const %s: &[(u32, u32)] = &[%s];" % (name, ", ".join(pairs)))
        else:
            lines.append("pub const %s: &[(u32, u32)] = &[" % name)
            for i in range(0, len(pairs), 4):
                lines.append("    " + ", ".join(pairs[i:i + 4]) + ",")
            lines.append("];")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


# ------------------------------------------------------------------ regions

def replace_region(text, begin, end, block, path):
    """Rewrite the marked region in text, markers included, with block."""
    lines = text.split("\n")
    begins = [i for i, l in enumerate(lines) if l.strip() == begin]
    ends = [i for i, l in enumerate(lines) if l.strip() == end]
    if len(begins) != 1 or len(ends) != 1:
        raise ClassesError(
            "%s: expected exactly one %r / %r region; found %d and %d. "
            "Insert the marker lines around the generated content first."
            % (path, begin, end, len(begins), len(ends)))
    if ends[0] <= begins[0]:
        raise ClassesError("%s: the %r marker comes before %r" % (path, end, begin))
    return "\n".join(lines[:begins[0]] + block.split("\n") + lines[ends[0] + 1:])


# --------------------------------------------------------------------- API

def load_classes(root):
    """Parse tools/core/classes.json; see the module docstring for the shape.

    Validation is deliberately strict and here rather than in the emitters:
    anything the data gets wrong should be one readable message, not half a
    regeneration followed by a syntax error somewhere else.
    """
    path = pathlib.Path(root) / CLASSES_PATH
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ClassesError("%s cannot be read: %s" % (path, e))
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise ClassesError("%s does not parse: %s" % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get("classes"), list):
        raise ClassesError("%s: expected an object with a \"classes\" array" % path)

    classes, seen = [], set()
    for i, entry in enumerate(data["classes"]):
        where = "%s: classes[%d]" % (path, i)
        if not isinstance(entry, dict):
            raise ClassesError("%s: expected an object" % where)
        cid, name, ranges = entry.get("id"), entry.get("name"), entry.get("ranges")
        if not isinstance(cid, str) or not cid:
            raise ClassesError("%s: \"id\" must be a non-empty string" % where)
        if not isinstance(name, str) or not name:
            raise ClassesError("%s: \"name\" must be a non-empty string" % where)
        if cid in seen:
            raise ClassesError("%s: duplicate class id '%s'" % (where, cid))
        seen.add(cid)
        if cid not in KNOWN:
            raise _unknown(cid)
        if not isinstance(ranges, list) or not ranges:
            raise ClassesError("%s: \"ranges\" must be a non-empty array" % where)
        parsed = []
        for j, pair in enumerate(ranges):
            if (not isinstance(pair, list) or len(pair) != 2
                    or not all(isinstance(s, str) and re.fullmatch(r"[0-9A-Fa-f]{4,5}", s)
                               for s in pair)):
                raise ClassesError(
                    "%s: ranges[%d] must be a [from, to] pair of 4 to 5 digit "
                    "hex strings" % (where, j))
            lo, hi = int(pair[0], 16), int(pair[1], 16)
            if lo > hi:
                raise ClassesError("%s: ranges[%d] runs backwards (%s > %s)"
                                   % (where, j, pair[0], pair[1]))
            if hi > 0x10FFFF:
                raise ClassesError("%s: ranges[%d] is past the last code point" % (where, j))
            parsed.append((lo, hi))
        classes.append({"id": cid, "name": name, "ranges": parsed})
    return classes


def targets(root, classes):
    """One (relpath, current_text, wanted_text) tuple per generated region."""
    root = pathlib.Path(root)
    out = []
    for relpath, begin, end, block in (
            (JS_PATH, JS_BEGIN, JS_END, js_block(classes)),
            (README_PATH, MD_BEGIN, MD_END, readme_block(classes)),
            (LLMS_PATH, MD_BEGIN, MD_END, llms_block(classes))):
        path = root / relpath
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ClassesError("%s cannot be read: %s" % (path, e))
        out.append((relpath, current, replace_region(current, begin, end, block, relpath)))
    return out


# --------------------------------------------------------------------- CLI

def main(argv=None):
    default_root = pathlib.Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Regenerate the decoder's generated regions from tools/core/classes.json.")
    parser.add_argument("root", nargs="?", default=None,
                        help="repository root (default: the checkout this script is in)")
    parser.add_argument("--check", action="store_true",
                        help="write nothing; print a diff and exit 1 if anything would change")
    parser.add_argument("--emit", choices=["rust"],
                        help="print a generated table to stdout instead of writing files")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root) if args.root else default_root

    try:
        classes = load_classes(root)
        if args.emit == "rust":
            sys.stdout.write(rust_tables(classes))
            return 0
        pending = targets(root, classes)
    except ClassesError as e:
        print("generate: %s" % e, file=sys.stderr)
        return 2

    changed = [(rel, cur, want) for rel, cur, want in pending if cur != want]

    if args.check:
        for rel, cur, want in changed:
            sys.stdout.writelines(difflib.unified_diff(
                cur.splitlines(keepends=True), want.splitlines(keepends=True),
                fromfile=rel, tofile=rel + " (generated)"))
        if changed:
            print("generate: %d file(s) out of date; run python3 tools/generate.py"
                  % len(changed), file=sys.stderr)
            return 1
        print("generate: ok")
        return 0

    for rel, cur, want in pending:
        if cur == want:
            print("%s: already current" % rel)
        else:
            (root / rel).write_text(want, encoding="utf-8")
            print("%s: regenerated" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
