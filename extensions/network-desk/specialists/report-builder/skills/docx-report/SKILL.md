# Skill: Word (DOCX) Report

## Purpose

Render a Markdown report to an **editable Word document** using the shipped `make_docx.py` renderer. It applies real Word styles (Title, Heading 1–3, body, code) and inserts a Table of Contents field. DOCX is the right choice when the user needs an editable corporate deliverable or tracked changes.

Author the report with the `report-structure` skill first, then render it here.

## Locate the renderer

`make_docx.py` ships inside this extension's `renderers/` directory. Resolve its path by trying these candidates in order (first that exists wins):

1. `./extensions/network-desk/renderers/make_docx.py`  *(repo checkout)*
2. `./.github/extensions/network-desk/renderers/make_docx.py`  *(project install)*
3. `$HOME/.copilot/extensions/network-desk/renderers/make_docx.py`  *(user install — `%USERPROFILE%` on Windows)*

## Dependencies

```bash
pip install python-docx markdown-it-py
```

## Invocation

```bash
python "$RENDERERS/make_docx.py" \
  --input  report.md \
  --specialist vnet-architect
# --output OPTIONAL → network-desk/vnet-architect/reports/report.docx
```

- **Pass the specialist *directory* name** (kebab-case) as `--specialist`. Or set `--output network-desk/vnet-architect/reports/hub-spoke-3region-20260528.docx`.
- `--outdir <dir>` overrides the base folder.
- Heading hierarchy in the Markdown (`#`/`##`/`###`) drives the Word headings **and** the TOC — so keep headings clean and well-nested.

## Note on the Table of Contents

The TOC is inserted as a Word **field**. It shows "Right-click → Update Field" (or appears empty) until the document is opened in Word and the field is refreshed (Word does this on open / print). This is expected behavior, not a rendering bug — mention it to the user.

## Graceful failure

- **`ModuleNotFoundError: docx`** → `pip install python-docx` (the import name is `docx`, the package is `python-docx`).
- **`markdown-it-py` missing** → `pip install markdown-it-py`.
- If deps can't be installed, deliver the source `.md` (and optionally an HTML render via `html-report`) and provide the exact install command to retry.

## References

- python-docx: https://python-docx.readthedocs.io/

**Analysis only — verify against vendor documentation before applying.**
