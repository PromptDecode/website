#!/usr/bin/env python3
"""Writes this site's "Built with" footer strip and subprocessors list from
tools/built-with.json, a vendored copy of this venture's entry in the Factory
Zero registry's stack.json (https://factory0.ventures/stack.json, generated
from Factory-Zero/website assets/fz-data.js). The site never fetches it at
runtime: the strip is static HTML between marker comments.

  python3 tools/built-with.py                 # rewrite the marked regions
  python3 tools/built-with.py --check         # exit 1 if a region is stale
  python3 tools/built-with.py --pull [SRC]    # refresh built-with.json from
                                              # stack.json (a path or URL;
                                              # default: the published one),
                                              # then rewrite

Regions (anywhere in any .html file outside dist/ and tools/):
  <!-- built-with:start --> ... <!-- built-with:end -->
      the footer strip: one line, every entry, planned ones marked "(planned)"
  <!-- subprocessors:start --> ... <!-- subprocessors:end -->
      the privacy page list: third parties that are live, then planned ones,
      labelled as planned

The markup uses the class names in CLASSES below; style them in the site's
own CSS. Edit the data in the registry, never here or in built-with.json by
hand: a change belongs in fz-data.js first, then `--pull`.
"""
import html
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "tools" / "built-with.json"
DEFAULT_SRC = "https://factory0.ventures/stack.json"
SKIP_DIRS = {"dist", "tools", "node_modules", ".git", ".wrangler", "design-src"}

CLASSES = {
    "strip": "built-with",
    "planned": "built-with__planned",
    "subs": "subprocessors",
}


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def esc(s):
    return html.escape(str(s), quote=True)


def strip_html(entry):
    parts = []
    for u in entry["uses"]:
        name = f'<a href="{esc(u["url"])}">{esc(u["name"])}</a>'
        planned = f' <span class="{CLASSES["planned"]}">(planned)</span>' if u["status"] == "planned" else ""
        parts.append(f'{esc(u["phrase"])} {name}{planned}')
    source = f'<a href="{esc(entry["page"])}">Factory Zero</a>'
    body = " &middot; ".join(parts)
    return f'<p class="{CLASSES["strip"]}">{body} &middot; Listed by {source}</p>'


def subprocessors_html(entry):
    third = [u for u in entry["uses"] if u["kind"] == "third-party"]
    sister = [u for u in entry["uses"] if u["kind"] == "factory-zero"]

    def item(u):
        tag = "" if u["status"] == "live" else " <em>(planned, not in use yet)</em>"
        note = f' {esc(u["note"])}' if u.get("note") else ""
        return f'<li><a href="{esc(u["url"])}">{esc(u["name"])}</a> ({esc(u["role"].replace("-", " "))}){tag}.{note}</li>'

    live = [u for u in third if u["status"] == "live"]
    planned = [u for u in third if u["status"] == "planned"]
    out = [f'<ul class="{CLASSES["subs"]}">']
    out += [item(u) for u in live + planned]
    out.append("</ul>")
    if sister:
        out.append(f'<p class="{CLASSES["subs"]}__sister">Factory Zero ventures this site uses or will use: '
                   + "; ".join(f'<a href="{esc(u["url"])}">{esc(u["name"])}</a> ({esc(u["role"].replace("-", " "))}'
                               + (", planned" if u["status"] == "planned" else "") + ")" for u in sister)
                   + f'. The full list, with what is live and what is planned, is in the <a href="{esc(entry["page"])}">Factory Zero registry</a>.</p>')
    return "\n".join(out)


REGIONS = {
    "built-with": strip_html,
    "subprocessors": subprocessors_html,
}


def rewrite(text, entry):
    for key, render in REGIONS.items():
        rx = re.compile(r"(<!-- %s:start -->)(.*?)(<!-- %s:end -->)" % (key, key), re.S)

        def sub(m):
            # keep the indentation of the start marker's line
            line_start = text.rfind("\n", 0, m.start()) + 1
            indent = re.match(r"[ \t]*", text[line_start:m.start()]).group(0)
            body = "\n".join(indent + l for l in render(entry).split("\n"))
            return f"{m.group(1)}\n{body}\n{indent}{m.group(3)}"

        text = rx.sub(sub, text)
    return text


def html_files():
    for p in sorted(ROOT.rglob("*.html")):
        rel = p.relative_to(ROOT)
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        yield p


def pull(src):
    if re.match(r"https?://", src):
        with urllib.request.urlopen(src, timeout=20) as r:
            stack = json.load(r)
    else:
        stack = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    cur = load()
    match = [v for v in stack["ventures"] if v["id"] == cur["id"]]
    if not match:
        sys.exit(f"{cur['id']} is not in {src}")
    entry = match[0]
    entry["source"] = stack.get("source", DEFAULT_SRC)
    DATA.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"built-with.json refreshed from {src}")


def main(argv):
    check = "--check" in argv
    if "--pull" in argv:
        i = argv.index("--pull")
        src = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("--") else DEFAULT_SRC
        pull(src)
    entry = load()
    for u in entry["uses"]:
        if u["status"] not in ("live", "planned"):
            sys.exit(f"built-with.json: status must be live or planned, not {u['status']!r}")
    found, stale = 0, []
    for p in html_files():
        text = p.read_text(encoding="utf-8")
        if "<!-- built-with:start -->" not in text and "<!-- subprocessors:start -->" not in text:
            continue
        found += 1
        new = rewrite(text, entry)
        if new != text:
            if check:
                stale.append(str(p.relative_to(ROOT)))
            else:
                p.write_text(new, encoding="utf-8")
                print(f"wrote {p.relative_to(ROOT)}")
    if not found:
        sys.exit("no built-with or subprocessors markers found in any page")
    if stale:
        sys.exit("built-with regions are stale (run python3 tools/built-with.py): " + ", ".join(stale))
    if check:
        print(f"built-with: {found} page(s) up to date")


if __name__ == "__main__":
    main(sys.argv[1:])
