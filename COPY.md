# Claims on the page, and what backs them

Most of what this site describes is now built: the decoder, the config and
content engines, and the open benchmark. The GitHub Action is written but
unreleased. What remains a plan is Living Brain's use of the content engine,
and pricing. This file keeps the
built and unbuilt apart, and records what was taken out of the design canvas
and why. When a plan ships, move it to "Facts", cite the file or URL that
proves it, and change its tense on the page.

## Facts

| Claim | Where | Backed by |
| :--- | :--- | :--- |
| The decoder works and runs in the browser | banner, `01 · Decode`, `llms.txt` | `assets/promptdecode.js`, `decodeText`. No backend exists to run it on |
| Nothing you paste is uploaded, stored or logged | decoder note, footer, `llms.txt` | The script contains no network call and `_headers` serves `connect-src 'none'`. `tools/check.py` fails on either changing |
| The three classes it reads | decoder note, `llms.txt` | The single source `tools/core/classes.json`, from which `tools/generate.py` writes the code, the README table and `llms.txt`. `tools/check.py` fails on any difference and runs the shared vectors in `tools/core/vectors.json` against the decoder |
| Tag-block characters mirror printable ASCII at U+E0000 | `01 · Decode` | Unicode 16.0, Tags block. Demonstrable in the decoder itself |
| A copied revealed pane still shows which characters were hidden | `01 · Decode` | The renderer brackets every hidden run with ⟪ ⟫ (U+27EA/U+27EB) and marks the run for assistive technology. The double angle brackets cannot appear in a decoded payload, which is ASCII, or in a U+XXXX hex label. `tools/check.py` fails if the brackets or the marking are dropped |
| The content engine is built and runs from source | engines lede, content card, `llms.txt` | `promptdecode-content`: repository walker, decoded findings, JSON and SARIF output (`PromptDecode/promptdecode`#9); `promptdecode scan` runs it (#11). No release yet |
| The GitHub Action is written and merged, and unreleased | Install section, `llms.txt` | `PromptDecode/action`#2 (https://github.com/PromptDecode/action), merged 2026-09-22. No tag, so `promptdecode/action@v1` does not resolve. It downloads a scanner release, and none exists yet |
| The benchmark is open, with a caveat on what it measures | `04 · What we claim`, `llms.txt` | https://github.com/PromptDecode/bench (PR #2, merged 2026-09-19) and its `results.json`. Corpus `promptdecode-bench`: 212 cases, 80 attack and 132 benign, every case written for the corpus. Its reference detector finds 80 of 80 attack and flags none of the 132 benign at every operating point; `results.json` says outright that this measures the corpus, not the detector |
| No cookies, no analytics | footer | `index.html` loads `promptdecode.js` and Google Fonts, nothing else. `tools/check.py` fails on any other third-party script |
| A Factory Zero venture | footer, JSON-LD, `llms.txt` | Factory Zero registry record FZ-009 (`Factory-Zero/website`, `assets/fz-data.js`) |
| "Built with" strip: Polar for payments and Keep Shipping for deploys, both **planned**; hosted on Cloudflare (the site, live) | footer of `index.html` and `404.html`, `llms.txt` | Factory Zero registry: the `uses` of FZ-009 in `Factory-Zero/website` `assets/fz-data.js`, published as https://factory0.ventures/stack.json and vendored in `tools/built-with.json`. Regenerate with `python3 tools/built-with.py --pull`; `tools/check.py` fails if the strip drifts from the vendored copy. Never edit the strip by hand |

## Plans (each carries a `planned` chip, or sits in a section that does)

Source for the remaining plans: the Claude Design canvas `promptdecode.dc.html`
(project `5b6b2917-7759-4ee9-883a-af2275c16303`). They are product intentions,
not specifications. The `config` and `content` engines and the `promptdecode
scan` CLI are built (source at `PromptDecode/promptdecode`, no release yet) and
carry the `shipping` chip.

- Pricing: free for public repositories, paid per developer for private ones.

## Illustrations (sample data, labelled on the page)

- Both terminal transcripts under `02 · Two engines`: `agent-review.yml`,
  `docs/CONTRIBUTING.md:42`, `README.md:7`, the HIGH and MED severities, the
  finding counts. The section says in its own lede that these are illustrations
  of an output format, not recordings.
- The decoder's sample text. It is a constructed pull request description with
  a tag-block payload built by the page's own script, not taken from a real
  repository or a real incident.

## Removed from the canvas

| Canvas said | Why it is not on the page |
| :--- | :--- |
| `$0` for public repos and `$8 per developer / month` for private | No price for anything planned, and both engines were a plan at the time. The shape stays ("Free" and "Paid"), the figures went. `tools/check.py` fails on anything that looks like a price |
| A **Copy** button on the workflow snippet | `promptdecode/action@v1` does not resolve. Copying it would hand someone a step that fails their run. The snippet is shown, chipped `not released`, with a sentence saying why |
| "Character-level evasion of commercial detectors runs 64 to 100% depending on technique" | A specific figure with no source to hand. The argument it supports (that a number moving that far is not a number) is stronger without it and is kept. Restore it only with a citation, in this table |
| Both engines described in the present tense ("Static taint analysis of GitHub Actions... Deterministic. No model. Zero cost per scan.") | Neither was built at the time. Conditional tense with a `planned` chip on each was used then; both are built now, run from source, and carry a `shipping` chip. The lede saying the transcripts are illustrations stays |
| "Zero cost per scan" | A pricing claim about software that does not exist |
| Footer links to `docs.promptdeco.de` and `github.com/promptdecode/benchmark` | Neither exists. Dead links. The footer lists only what resolves, and `tools/check.py` holds the list of the ones that do not |
| `promptdecode · 2026` beside links to Docs and Benchmark | Kept the line, dropped the two dead links |
| Em-dashes throughout the copy, in the section eyebrows ("01", dash, "Decode") and the title | House style across the Factory Zero sites. Middle dots and full stops instead; `tools/check.py` fails on all three spellings, in this file too, which is why the glyph is described here rather than shown |
| A theme transition on `body` (`transition: background 200ms, color 200ms`) | Chrome does not restart a transition whose end value comes from a custom property that changed on an ancestor, so half the page kept its old colours and the light theme visibly did not apply. Transitions are suppressed for the frame the theme flips in; see the note in `assets/promptdecode.css` |

## The one claim this project cannot get wrong

"If a class is not on the list, we do not detect it. The list is the claim."

That sentence makes the list of Unicode classes a promise rather than a
description, so the list has one source, `tools/core/classes.json`:
`tools/generate.py` writes the constants in `assets/promptdecode.js`, the
README table and `llms.txt` from it, and `tools/check.py` regenerates all
three and fails on any difference, in either direction, then runs the shared
vectors in `tools/core/vectors.json` against the decoder. Adding a class means
editing `tools/core/classes.json` and running `python3 tools/generate.py`, in
one diff.

## Sister ventures

| Claim | Where | Source |
| :--- | :--- | :--- |
| Planned in Living Brain: the content engine screens everything the brain reads and serves to coding agents | Engines section, llms.txt | Livingbrain-wiki/livingbrain#50 (2026-10-03). Planned, conditional wording |
