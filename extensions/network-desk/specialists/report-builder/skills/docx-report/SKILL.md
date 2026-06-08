# Skill: Word (DOCX) Whitepaper

## Purpose

Render a Markdown report to a **professional, editable Word whitepaper** using the
shipped `make_docx.py` renderer. It produces a cover page, real Word styles
(Title, Heading 1–3, List Bullet/Number, Quote, Table Grid), real inline runs for
`**bold**` / `*italic*` / `` `code` `` / clickable `[links](url)`, embedded
Mermaid diagrams, a Table-of-Contents field, and a footer with a live page number.
DOCX is the right choice when the user needs an editable corporate deliverable or
tracked changes.

Author the report with the `report-structure` skill first (it documents the
front-matter block this renderer consumes), then render it here.

## Locate the renderer

`make_docx.py` ships inside this extension's `renderers/` directory (alongside the
shared `_common.py` helper module — keep them together). Resolve the path by
trying these candidates in order (first that exists wins):

1. `./extensions/network-desk/renderers/make_docx.py`  *(repo checkout)*
2. `./.github/extensions/network-desk/renderers/make_docx.py`  *(project install)*
3. `$HOME/.copilot/extensions/network-desk/renderers/make_docx.py`  *(user install — `%USERPROFILE%` on Windows)*

In the **generated plugin**, the renderers live under
`./reference/renderers/make_docx.py` of the `network-desk-doc` skill.

## Dependencies

```bash
pip install python-docx markdown-it-py
```

The renderer uses **only** these two packages (plus the Python standard library).
Front-matter is parsed by a built-in minimal parser — **no PyYAML required**.

Mermaid diagrams additionally need the **local Mermaid CLI** (optional — see below).

## Invocation

```bash
python "$RENDERERS/make_docx.py" \
  --input  report.md \
  --specialist vnet-architect
# --output OPTIONAL → network-desk/vnet-architect/reports/report.docx
```

- **Pass the specialist *directory* name** (kebab-case) as `--specialist`. It labels
  the footer/header — it is **never** used as the document title.
- `--output network-desk/vnet-architect/reports/hub-spoke-3region-20260528.docx` sets
  an explicit path; `--outdir <dir>` overrides only the base folder.
- Heading hierarchy in the Markdown (`#`/`##`/`###`) drives the Word headings **and**
  the TOC — keep headings clean and well-nested.

### Cover-page overrides

The cover title/subtitle/metadata are sourced in this precedence:
**YAML front-matter → CLI flag → first `# H1`** (for the title). Provide a
front-matter block at the very top of the Markdown:

```markdown
---
title: Hub-and-Spoke Network Design
subtitle: Azure VNet Architecture Review
classification: Confidential
version: "1.2"
author: Network Desk
---
```

…or override per-run with flags: `--title --subtitle --classification --version
--author`. The metadata block prints Classification / Version / Author / Date
(date defaults to today) — empty fields are omitted.

## Inline formatting & hyperlinks

`**bold**`, `*italic*`, `` `code` ``, `~~strike~~`, and `[text](url)` are rendered
as **real Word runs and clickable hyperlinks everywhere** — paragraphs, headings,
list items, blockquotes, and table cells. No literal `**`, backticks, or `[]()`
appear in the output. HTML entities (`&mdash;`, `&amp;`, …) are decoded.

## Mermaid diagrams → embedded PNG

```` ```mermaid ```` fenced blocks are rendered to PNG using **only the local
Mermaid CLI** — `mmdc`, falling back to `npx -y @mermaid-js/mermaid-cli`. Each
diagram is embedded as a centered ~6.3in image with a **"Figure N."** caption; the
`.mmd` source and `.png` are saved under `network-desk/<specialist>/diagrams/`.

If the CLI is unavailable the renderer **fails gracefully**: it emits a
`Figure N. [diagram omitted]` caption, lists the raw Mermaid source in an
**Appendix: Diagram Sources**, and prints the exact install command to stderr. It
**never** dumps the diagram source inline and **never** calls a hosted/external
service. To enable embedding:

```bash
npm install -g @mermaid-js/mermaid-cli
```

## Styling

Calibri body; **navy** (`#0e5a9c`) Title/Heading 1; **blue** (`#1f6fb2`) Heading
2/3 + subtitle + the cover accent rule; **shaded navy** table header rows with
white text. Emojis are stripped while technical arrows (`->`, `→`) are preserved.

## Note on the Table of Contents & page numbers

The TOC and footer page number are inserted as Word **fields**. They show a
placeholder ("Right-click → Update Field") until the document is opened in Word and
fields are refreshed (Word does this automatically on open / print). The renderer
sets `updateFields=true` so Word rebuilds them on open. This is expected behavior,
not a rendering bug — mention it to the user.

## Graceful failure

- **`ModuleNotFoundError: docx`** → `pip install python-docx` (import name is `docx`, package is `python-docx`).
- **`markdown-it-py` missing** → `pip install markdown-it-py`.
- **Mermaid CLI missing** → diagrams are omitted with an appendix + install command (above); the DOCX still renders.
- If deps can't be installed, deliver the source `.md` (and optionally an HTML render via `html-report`) and provide the exact install command to retry.

## References

- python-docx: https://python-docx.readthedocs.io/
- Mermaid CLI: https://github.com/mermaid-js/mermaid-cli

**Analysis only — verify against vendor documentation before applying.**
