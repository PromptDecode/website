#!/usr/bin/env python3
"""Checks the site before it ships. Zero dependencies; run from anywhere:

    python3 tools/check.py            # checks the repository this file is in
    python3 tools/check.py <root>     # checks another checkout (deploy.sh does this)

The checks:

Structural: in-page anchors resolve, ids are unique, local assets exist,
JSON-LD parses, and no third-party script sneaks onto the page.

The house rules from the README, as far as a script can enforce them: no price
figures, nothing badged Available or Beta, a `planned` chip on every engine and
every tier, the not-built banner intact, no link to a repository or subdomain
that does not exist yet, and no em-dashes in the copy.

And the two promises that are specific to this project, which are worth more
than the rest put together:

  * The page says nothing you paste leaves your browser. So the page's own
    script, `assets/promptdecode.js`, may not contain a network call, and
    `_headers` must serve `connect-src 'none'`. The promise binds the page,
    not the tooling that keeps the page honest: this script talks to the
    network itself, in the pinned-release leg below, and that takes nothing
    away from what the page promises about its own script.
  * The page says the list of Unicode classes IS the claim. So the ranges the
    decoder actually implements must be the ranges named in `llms.txt`. A class
    quietly dropped from the code while the prose still promises it is the one
    failure this project cannot survive. The list has one source now,
    `tools/core/classes.json`, kept under `tools/core/` until
    promptdecode-core publishes a release to pin (see `tools/core/pin.json`),
    and three legs hold the promise against the three ways that pipeline can
    drift:

      - Regeneration. `tools/generate.py` writes the constants in
        `assets/promptdecode.js`, the table in README.md and the list in
        `llms.txt` from `classes.json`; this script regenerates all three in
        memory and fails on any difference, so a hand edit to a generated
        region cannot ship. Always runs; needs no network.
      - The shared vectors. `tools/core/vectors.json` runs against the decoder
        with `node tools/vectors.mjs`, so the claim is tested against the
        decoder's behaviour and not only its spelling. Skipped when node is
        not installed: a contributor without node must not be blocked. But the
        runner and the vectors are committed files, so either going missing is
        the repository being broken, not the environment lacking a tool, and
        that is a failure: a gate that can be deleted while the check stays
        green is the one failure this project cannot survive.
      - The pinned release. When `tools/core/pin.json` names a tag, this
        script fetches that release's `classes.json` and `vectors.json` and
        fails if the vendored copy has drifted from it. No release exists to
        pin yet, so the tag is empty and the leg says so and moves on. Every
        fetch problem (no network, DNS, timeout, a 404 tag, a non-JSON
        response) is a skip with its reason; only a fetch that succeeds and
        disagrees with `tools/core/` is a failure. The check must pass with
        no network at all. The pin file itself is committed, so a pin that
        names a tag but no repository is a broken file and fails.

The same line runs through every file these legs read. What is committed has
to be present and parseable: when it is not, that is a failure with the path
named, never a skip and never a traceback, so the summary line always prints.
What is absent from the environment (node, the network) is a skip with its
reason. The first kind of problem is ours to fix; the second belongs to the
machine the check happens to run on.

A skip prints SKIP, names its reason, and is never counted. Exit status is the
number of failures (0 = all good).
"""
import difflib
import http.client
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent)
PAGES = ["index.html", "404.html"]
ALLOWED_HOSTS = {"promptdeco.de", "fonts.googleapis.com", "fonts.gstatic.com"}  # itself (canonical), and Google Fonts

failures = []


def fail(msg):
    failures.append(msg)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.hrefs, self.local, self.remote = [], [], [], []
        self.jsonld, self._in_jsonld = [], False
        self.text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        for attr in ("href", "src"):
            v = a.get(attr)
            if not v:
                continue
            if v.startswith("#"):
                self.hrefs.append(v[1:])
            elif v.startswith("/") and not v.startswith("//"):
                self.local.append(v.split("?")[0].split("#")[0])
            elif v.startswith("https://") and tag in ("script", "link", "img", "iframe"):
                self.remote.append((tag, v))
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_jsonld:
            self.jsonld.append(data)
        else:
            self.text.append(data)


def parse(name):
    p = Page()
    p.feed((ROOT / name).read_text(encoding="utf-8"))
    return p


# ------------------------------------------------------------------ structure
for name in PAGES:
    p = parse(name)
    dupes = sorted({i for i in p.ids if p.ids.count(i) > 1})
    if dupes:
        fail(f"{name}: duplicate ids {dupes}")
    for h in p.hrefs:
        if h and h not in p.ids:
            fail(f"{name}: link to #{h}, but no element has that id")
    for path in p.local:
        if path == "/":
            continue
        if not (ROOT / path.lstrip("/")).exists():
            fail(f"{name}: {path} does not exist")
    for tag, url in p.remote:
        host = re.sub(r"^https://([^/]+).*$", r"\1", url)
        if host not in ALLOWED_HOSTS:
            fail(f"{name}: third-party <{tag}> from {host}; the page loads nothing but Google Fonts")
    for block in p.jsonld:
        try:
            json.loads(block)
        except ValueError as e:
            fail(f"{name}: JSON-LD does not parse: {e}")

try:
    json.loads((ROOT / "site.webmanifest").read_text(encoding="utf-8"))
except ValueError as e:
    fail(f"site.webmanifest: does not parse: {e}")

index_html = (ROOT / "index.html").read_text(encoding="utf-8")
index = parse("index.html")
visible = " ".join(index.text)
js = (ROOT / "assets/promptdecode.js").read_text(encoding="utf-8")
headers = (ROOT / "_headers").read_text(encoding="utf-8")
llms = (ROOT / "llms.txt").read_text(encoding="utf-8")

# ------------------------------------------------- nothing you paste leaves
# The page's strongest claim, and the cheapest one to break by accident.
for call in (r"\bfetch\s*\(", r"XMLHttpRequest", r"sendBeacon", r"new\s+WebSocket", r"EventSource", r"import\s*\("):
    if re.search(call, js):
        fail(f"assets/promptdecode.js: contains {call!r}; the page promises that nothing you paste leaves the browser")
if "connect-src 'none'" not in headers:
    fail("_headers: connect-src is not 'none'; the decoder's privacy claim is no longer enforced by the browser")
if "no cookies" not in visible.lower():
    fail("index.html: the footer lost its no-cookies line")

# ------------------------------------------------------- the list is the claim
# Every range the decoder implements has to be a range llms.txt names, in the
# U+ spelling a reader would check it against.
implemented = {int(m, 16) for m in re.findall(r"0x([0-9A-Fa-f]{4,5})\b", js)}
for cp in sorted(implemented):
    spelled = f"U+{cp:04X}"
    if spelled not in llms:
        fail(f"llms.txt: the decoder handles {spelled} but llms.txt does not name it; the list is the claim")
for spelled in sorted(set(re.findall(r"U\+([0-9A-F]{4,5})\b", llms))):
    if int(spelled, 16) not in implemented:
        fail(f"llms.txt: promises {spelled}, which assets/promptdecode.js does not implement")

# -------------------------------------------- one source, three spellings
# The list has one source now: tools/core/classes.json, kept under
# tools/core/ until promptdecode-core publishes a release to pin against.
# tools/generate.py writes the three
# spellings of the claim from it (the constants in assets/promptdecode.js,
# the table in README.md, the list in llms.txt), and the three legs below
# fail on the three ways that pipeline can drift: a generated region edited
# by hand, a decoder that disagrees with the shared vectors, and a copy in
# tools/core/ left behind by the release pinned in tools/core/pin.json.
#
# generate.py lives next to this script, so sys.path gets that directory and
# not ROOT's tools/: the import has to survive deploy.sh copying the tree
# elsewhere and running `python3 $tmp/tree/tools/check.py $tmp/tree`, where
# the script and the root are the same copied tree. The import is the only
# thing this check writes to disk, and it should not even do that: a check
# that litters tools/__pycache__ into whatever checkout ran it is its own
# house-rule violation.
sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
# The import is guarded because tools/generate.py is a committed input, not an
# optional dependency: missing or broken, it is the repository being broken,
# and that is a counted failure with the reason, not a traceback that dies
# before the summary line.
try:
    import generate
except Exception as e:  # a missing file, or one that does not even parse
    generate = None
    fail(f"tools/generate.py: cannot be imported: {type(e).__name__}: {e}")

# Leg 1: the generated regions are current. Always runs, needs no network.
# ClassesError is the generator's own "a human has to fix this" message; any
# other exception out of it is a bug in the generator, which is still a
# failure, still counted, and still named rather than a traceback.
if generate is not None:
    try:
        for relpath, current, wanted in generate.targets(ROOT, generate.load_classes(ROOT)):
            if current == wanted:
                continue
            diff = list(difflib.unified_diff(
                current.splitlines(keepends=True), wanted.splitlines(keepends=True),
                fromfile=relpath, tofile=relpath + " (generated)"))
            report = [f"{relpath}: the generated region is not what tools/generate.py "
                      f"produces from tools/core/classes.json; run python3 tools/generate.py"]
            report += [line.rstrip("\n") for line in diff[:20]]
            if len(diff) > 20:
                report.append(f"(diff capped at 20 lines; {len(diff) - 20} more)")
            fail("\n".join(report))
    except generate.ClassesError as e:
        fail(str(e))
    except Exception as e:
        fail(f"tools/generate.py: failed while regenerating: {type(e).__name__}: {e}")

# Leg 2: the shared vectors run against the decoder. The order of the two
# guards is the policy: tools/vectors.mjs is committed, so its absence is the
# repository being broken and fails even on a machine that has no node, while
# node itself is the environment and a contributor without it must not be
# blocked. A runner that hangs is not a skip either: a vector suite that never
# finishes says nothing either way, and silence must not be allowed to read as
# a pass.
runner = ROOT / "tools" / "vectors.mjs"
node = shutil.which("node")
if not runner.exists():
    fail("tools/vectors.mjs: missing. It is a committed file, so this is the "
         "repository being broken rather than an environment missing node, and "
         "the shared vectors in tools/core/vectors.json are going unrun")
elif node is None:
    print("SKIP vectors: node is not installed, so the shared vectors in "
          "tools/core/vectors.json did not run against assets/promptdecode.js")
else:
    try:
        run = subprocess.run([node, str(runner), str(ROOT)],
                             capture_output=True, text=True, errors="replace",
                             timeout=60)
    except subprocess.TimeoutExpired:
        fail("tools/vectors.mjs: no result within 60s; the shared vectors did not "
             "finish, which is a failure and not a skip")
    except OSError as e:
        fail(f"tools/vectors.mjs: could not be run: {e}")
    else:
        if run.returncode != 0:
            output = (run.stdout + run.stderr).strip() or "(no output)"
            fail("tools/core/vectors.json: the shared vectors failed against "
                 "assets/promptdecode.js (node tools/vectors.mjs):\n" + output)

# Leg 3: the vendored copy still matches the pinned release. Every fetch
# problem is a skip, never a failure: check.py has to pass on a machine with
# no network, and an unreachable or vanished release must not block a commit
# that has nothing to do with it. Only a fetch that succeeds and disagrees
# with tools/core/ means the vendored source of truth has drifted, and that
# is a failure.
# The file is read as text first so that a pin.json holding a bare `null`
# (which parses, to Python None) cannot pass for an absent check: only a file
# that truly could not be read leaves the leg silent, and that path has
# already failed above.
pin, pin_text = None, None
try:
    pin_text = (ROOT / "tools" / "core" / "pin.json").read_text(encoding="utf-8")
except OSError as e:
    fail(f"tools/core/pin.json: cannot be read: {e}")
try:
    if pin_text is not None:
        pin = json.loads(pin_text)
except ValueError as e:
    fail(f"tools/core/pin.json: does not parse: {e}")

if isinstance(pin, dict):
    repo, tag = pin.get("repo", ""), pin.get("tag", "")
    if not isinstance(repo, str) or not isinstance(tag, str):
        fail("tools/core/pin.json: \"repo\" and \"tag\" must be strings")
    elif not tag:
        print("SKIP pinned: promptdecode-core has published no release yet, so "
              "tools/core/ is the source until one exists. Setting tag in "
              "tools/core/pin.json turns this leg on")
    elif not repo:
        # A tag with nowhere to fetch it from is not a fetch problem, it is a
        # broken pin, and skips must stay reserved for the world being
        # unreachable rather than for files we ship being wrong.
        fail("tools/core/pin.json: names a tag but \"repo\" is empty; the leg "
             "has no release to compare tools/core/ against")
    else:
        for name in ("classes.json", "vectors.json"):
            url = f"https://raw.githubusercontent.com/{repo}/{tag}/{name}"
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    upstream = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, http.client.HTTPException,
                    OSError, ValueError) as e:
                # HTTPException covers a response that dies mid-read, which is
                # a fetch problem like any other, not a crash.
                print(f"SKIP pinned: could not fetch {url} ({e}); the vendored "
                      f"tools/core/{name} was not compared")
                continue
            try:
                vendored = json.loads(
                    (ROOT / "tools" / "core" / name).read_text(encoding="utf-8"))
            except OSError as e:
                fail(f"tools/core/{name}: cannot be read: {e}")
                continue
            except ValueError as e:
                fail(f"tools/core/{name}: does not parse: {e}")
                continue
            if upstream != vendored:
                fail(f"tools/core/{name}: drifted from the pinned release {repo}@{tag}. "
                     "Update tools/core/ from that release and run python3 tools/generate.py")
elif pin_text is not None:
    # Covers both a JSON null and any other non-object the file could hold.
    fail("tools/core/pin.json: expected an object with \"repo\" and \"tag\"")

# ------------------------------------------------------------------ house rules

# 1. No price for anything planned.
for m in re.finditer(r"[$€£]\s?\d|\d\s?(USD|EUR|GBP)\b|/\s?(mo|month)\b", visible):
    fail(f"index.html: looks like a price: {visible[max(0, m.start() - 30):m.end() + 30]!r}")

# 2. No status that claims availability.
for m in re.finditer(r">\s*(Available|Beta|Popular|Live now|GA)\s*<", index_html):
    fail(f"index.html: status badge {m.group(1)!r}; only the decoder and the config engine are available, so nothing else may say so")


# 3. Every engine and every tier carries a status chip; the decoder and the
#    config engine are the two things allowed to say shipping.
def cards(cls, closing):
    return [c.split(closing)[0] for c in re.split(r'class="' + re.escape(cls) + r'"', index_html)[1:]]


for cls, closing in (("engine", "</article>"), ("tier", "</div>")):
    found = cards(cls, closing)
    if not found:
        fail(f"index.html: no .{cls} cards found")
    for n, card in enumerate(found, 1):
        if "chip--planned" not in card and "chip--shipping" not in card:
            fail(f"index.html: .{cls} #{n} has no status chip")
if index_html.count("chip--shipping") != 2:
    fail("index.html: exactly two things ship (the decoder and the config engine); found "
         f"{index_html.count('chip--shipping')} shipping chips")

# 4. The banner says what is and is not built.
if "The decoder on this page works" not in index_html:
    fail("index.html: the built/unbuilt banner is missing")

# 5. No dead controls and no links to things that do not exist. The Action, the
#    benchmark repository and the docs subdomain are all planned; linking to
#    them hands a reader a 404 dressed as a product.
# `PromptDecode/action` and `PromptDecode/bench` were created on 2026-09-19 and
# came off this list then; the backlog section links their trackers. The docs
# subdomain and the old `benchmark` spelling still resolve nowhere.
for dead in ("docs.promptdeco.de", "github.com/promptdecode/benchmark",
             "github.com/PromptDecode/benchmark"):
    if f'href="https://{dead}' in index_html or f'href="http://{dead}' in index_html:
        fail(f"index.html: links to {dead}, which does not exist yet")
if re.search(r"<button[^>]*>\s*copy\s*<", index_html, re.I):
    fail("index.html: a copy button for the workflow snippet; the Action does not exist, so copying it hands "
         "someone a step that fails the run")

# 6. House style: no em-dashes, in any spelling.
for path in ("index.html", "404.html", "llms.txt", "README.md", "COPY.md"):
    f = ROOT / path
    if not f.exists():
        continue
    body = f.read_text(encoding="utf-8")
    for spelling in ("—", "&mdash;", "&#8212;"):
        if spelling in body:
            fail(f"{path}: contains an em-dash ({spelling!r}); the house style uses a middle dot or a full stop")

# 7. The deploy config still points at the built output.
#    `wrangler pages project create` scaffolds this file with `"directory": "."`,
#    which publishes the whole repository. It did, on 2026-09-18.
wrangler = ROOT / "wrangler.jsonc"
if not wrangler.exists():
    fail("wrangler.jsonc is missing; deploy.sh needs it to know what to upload")
else:
    # jsonc: strip whole-line // comments, which is all this file uses.
    raw = "\n".join(l for l in wrangler.read_text(encoding="utf-8").splitlines()
                    if not l.lstrip().startswith("//"))
    try:
        cfg = json.loads(raw)
    except ValueError as e:
        fail(f"wrangler.jsonc: does not parse: {e}")
    else:
        directory = cfg.get("assets", {}).get("directory")
        if directory != "dist":
            fail(f"wrangler.jsonc: assets.directory is {directory!r}, not 'dist'; "
                 "a deploy would publish that directory verbatim, allowlist and all")
        if cfg.get("name") != "promptdecode":
            fail(f"wrangler.jsonc: name is {cfg.get('name')!r}, not 'promptdecode'; "
                 "deploying under another name publishes a second Worker at a different URL")

# 8. llms.txt keeps its guard.
if "PLANNED" not in llms or "## Shipping today" not in llms:
    fail("llms.txt: lost the built/unbuilt split")

# 9. A copied revealed pane still marks what was hidden. The reveal is a
#    page promise, so the script that ships it holds it: every hidden run
#    must be bracketed with the U+27EA/U+27EB characters, and the run must
#    be marked for assistive technology so it is announced as hidden rather
#    than read as prose.
if "⟪" not in js or "⟫" not in js:
    fail("assets/promptdecode.js: hidden runs would lose the distinction in a plain-text copy; the U+27EA/U+27EB markers are missing")
if not (re.search(r'setAttribute\(\s*"role",\s*"img"\)', js) and re.search(r'setAttribute\(\s*"aria-label"', js)):
    fail("assets/promptdecode.js: hidden runs are not marked for assistive technology; the role=img aria-label is missing")
copy_md = (ROOT / "COPY.md").read_text(encoding="utf-8")
if "⟪" not in copy_md or "⟫" not in copy_md:
    fail("COPY.md: does not record the ⟪ ⟫ markers that keep a copied reveal readable")

for f in failures:
    print("FAIL", f)
print(f"{len(failures)} failure(s)" if failures else "check: ok")
sys.exit(len(failures))
