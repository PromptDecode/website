#!/usr/bin/env python3
"""Checks the site before it ships. Zero dependencies; run from anywhere:

    python3 tools/check.py            # checks the repository this file is in
    python3 tools/check.py <root>     # checks another checkout (deploy.sh does this)

Three kinds of check.

Structural: in-page anchors resolve, ids are unique, local assets exist,
JSON-LD parses, and no third-party script sneaks onto the page.

The house rules from the README, as far as a script can enforce them: no price
figures, nothing badged Available or Beta, a `planned` chip on every engine and
every tier, the not-built banner intact, no link to a repository or subdomain
that does not exist yet, and no em-dashes in the copy.

And the two promises that are specific to this project, which are worth more
than the rest put together:

  * The page says nothing you paste leaves your browser. So the script may not
    contain a network call, and `_headers` must serve `connect-src 'none'`.
  * The page says the list of Unicode classes IS the claim. So the ranges the
    decoder actually implements must be the ranges named in `llms.txt`. A class
    quietly dropped from the code while the prose still promises it is the one
    failure this project cannot survive.

Exit status is the number of failures (0 = all good).
"""
import json
import pathlib
import re
import sys
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

for f in failures:
    print("FAIL", f)
print(f"{len(failures)} failure(s)" if failures else "check: ok")
sys.exit(len(failures))
