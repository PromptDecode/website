# Claims on the page, and what backs them

One thing on this site is built, and the rest is a plan. This file keeps the two
apart, and records what was taken out of the design canvas and why. When a plan
ships, move it to "Facts", cite the file or URL that proves it, and change its
tense on the page.

## Facts

| Claim | Where | Backed by |
| :--- | :--- | :--- |
| The decoder works and runs in the browser | banner, `01 · Decode`, `llms.txt` | `assets/promptdecode.js`, `decodeText`. No backend exists to run it on |
| Nothing you paste is uploaded, stored or logged | decoder note, footer, `llms.txt` | The script contains no network call and `_headers` serves `connect-src 'none'`. `tools/check.py` fails on either changing |
| The three classes it reads | decoder note, `llms.txt` | The single source `tools/core/classes.json`, from which `tools/generate.py` writes the code, the README table and `llms.txt`. `tools/check.py` fails on any difference and runs the shared vectors in `tools/core/vectors.json` against the decoder |
| Tag-block characters mirror printable ASCII at U+E0000 | `01 · Decode` | Unicode 16.0, Tags block. Demonstrable in the decoder itself |
| Nothing else is built | banner, every `planned` chip, `llms.txt` | `github.com/PromptDecode` held no repository other than this site when the page was written |
| No cookies, no analytics | footer | `index.html` loads `promptdecode.js` and Google Fonts, nothing else. `tools/check.py` fails on any other third-party script |
| A Factory Zero venture | footer, JSON-LD, `llms.txt` | Pending: the Factory Zero registry entry has not been added yet (`Factory-Zero/website`, `assets/fz-data.js`) |

## Plans (each carries a `planned` chip, or sits in a section that does)

Source for every plan: the Claude Design canvas `promptdecode.dc.html` (project
`5b6b2917-7759-4ee9-883a-af2275c16303`). They are product intentions, not
specifications, and no code exists for any of them.

- A `config` engine: static taint analysis of GitHub Actions workflows.
- A `content` engine: the decoder's rules across a whole repository.
- A command-line scanner, `promptdecode scan`.
- A GitHub Action, `promptdecode/action@v1`, posting check annotations.
- An open benchmark: a named corpus and harness.
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
| `$0` for public repos and `$8 per developer / month` for private | No price for anything planned, and both engines are planned. The shape stays ("Free" and "Paid"), the figures went. `tools/check.py` fails on anything that looks like a price |
| A **Copy** button on the workflow snippet | `promptdecode/action@v1` does not resolve. Copying it would hand someone a step that fails their run. The snippet is shown, chipped `planned`, with a sentence saying why |
| "Character-level evasion of commercial detectors runs 64 to 100% depending on technique" | A specific figure with no source to hand. The argument it supports (that a number moving that far is not a number) is stronger without it and is kept. Restore it only with a citation, in this table |
| Both engines described in the present tense ("Static taint analysis of GitHub Actions... Deterministic. No model. Zero cost per scan.") | Neither is built. Conditional tense, a `planned` chip on each, and a lede saying the transcripts are illustrations |
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
