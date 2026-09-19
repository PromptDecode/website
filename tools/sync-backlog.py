#!/usr/bin/env python3
"""Rewrites the backlog section of index.html from the real issue trackers.

    python3 tools/sync-backlog.py            # rewrite, then report
    python3 tools/sync-backlog.py --check    # fail if the page is out of date

A hand-written backlog is a lie within a week, so this one is generated. It
reads the open issues from the repositories listed in REPOS with `gh`, and
replaces everything between the backlog markers in index.html. Nothing else in
the page is touched.

Requires `gh` to be authenticated. With no network it leaves the page alone and
says so rather than emptying the section: an unreachable tracker is not the
same as an empty backlog, and shipping "nothing planned" because a token
expired would be worse than being a day stale.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
START = "<!-- backlog:start -->"
END = "<!-- backlog:end -->"

# Repository, and the label shown on the page. Order is the order on the page.
REPOS = [
    ("PromptDecode/promptdecode", "engines"),
    ("PromptDecode/action", "action"),
    ("PromptDecode/bench", "benchmark"),
    ("PromptDecode/website", "site"),
]


def is_private(repo):
    """A private repository's issue links 404 for a visitor, so they are listed
    by title and not linked. Publishing a link that only we can open would be
    worse than publishing none."""
    out = subprocess.run(
        ["gh", "repo", "view", repo, "--json", "isPrivate"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"{repo}: {out.stderr.strip()[:200]}")
    return bool(json.loads(out.stdout or "{}").get("isPrivate"))


def issues(repo):
    out = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--state", "open",
         "--limit", "50", "--json", "number,title,url"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"{repo}: {out.stderr.strip()[:200]}")
    return sorted(json.loads(out.stdout or "[]"), key=lambda i: i["number"])


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def render(groups):
    total = sum(len(v) for _, _, _, v in groups)
    rows = []
    for repo, label, private, items in groups:
        if not items:
            continue
        note = ' <span class="backlog__priv">private</span>' if private else ""
        rows.append(f'      <p class="backlog__repo">{esc(label)}{note}</p>')
        rows.append('      <ul class="backlog__list">')
        for i in items:
            no = f'<span class="backlog__no">#{i["number"]}</span>'
            if private:
                rows.append(f'        <li><span>{no}{esc(i["title"])}</span></li>')
            else:
                rows.append(
                    f'        <li><a href="{esc(i["url"])}">{no}{esc(i["title"])}</a></li>'
                )
        rows.append("      </ul>")
    body = "\n".join(rows)
    return (
        f"{START}\n"
        f'      <p class="lede">{total} open, across four repositories. '
        f"This list is generated from the trackers, so it is what is actually "
        f"open rather than what someone remembered to write down.</p>\n"
        f"{body}\n"
        f"      {END}"
    )


def main():
    check = "--check" in sys.argv
    page = PAGE.read_text(encoding="utf-8")
    if START not in page or END not in page:
        sys.exit("index.html has no backlog markers")

    try:
        groups = [(r, label, is_private(r), issues(r)) for r, label in REPOS]
    except Exception as e:
        print(f"could not read the trackers ({e}); leaving the page as it is")
        return 0 if not check else 0

    new = render(groups)
    old = re.search(re.escape(START) + r".*?" + re.escape(END), page, re.S).group(0)
    if old.strip() == new.strip():
        print(f"backlog: up to date ({sum(len(v) for _, _, _, v in groups)} open)")
        return 0
    if check:
        print("backlog: out of date; run tools/sync-backlog.py", file=sys.stderr)
        return 1
    PAGE.write_text(page.replace(old, new), encoding="utf-8")
    print(f"backlog: rewritten ({sum(len(v) for _, _, _, v in groups)} open)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
