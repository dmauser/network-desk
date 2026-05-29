# Skill: PDF Report

## Purpose

Render a Markdown report to a **print-ready PDF** using the shipped `make_pdf.py` renderer (Playwright + headless Chromium for faithful, fixed layout). PDF is the right choice for stakeholder/executive hand-off and printing.

Author the report with the `report-structure` skill first, then render it here.

## Locate the renderer

`make_pdf.py` ships inside this extension's `renderers/` directory. Resolve its path by trying these candidates in order (first that exists wins):

1. `./extensions/network-desk/renderers/make_pdf.py`  *(repo checkout)*
2. `./.github/extensions/network-desk/renderers/make_pdf.py`  *(project install)*
3. `$HOME/.copilot/extensions/network-desk/renderers/make_pdf.py`  *(user install — `%USERPROFILE%` on Windows)*

## Dependencies

```bash
pip install playwright markdown2
python -m playwright install chromium   # one-time browser download (~100+ MB)
```

## Invocation

```bash
python "$RENDERERS/make_pdf.py" \
  --input  report.md \
  --specialist pricing-analyst
# --output OPTIONAL → network-desk/pricing-analyst/reports/report.pdf
```

- **Pass the specialist *directory* name** (kebab-case) as `--specialist` so the default output path matches the convention. Or pass an explicit `--output network-desk/pricing-analyst/reports/nat-egress-comparison-20260528.pdf`.
- `--outdir <dir>` overrides the base folder.

## Graceful failure (important — PDF has the heaviest dependencies)

1. **`markdown2` / `playwright` not installed** → `pip install playwright markdown2`.
2. **Chromium not installed** (`Executable doesn't exist…`) → `python -m playwright install chromium`.
3. **Chromium download blocked / sandboxed environment** → **fall back to HTML**: render the same Markdown with the `html-report` skill (`make_html.py`, only needs `markdown2`), deliver the `.html`, and tell the user it can be "Print → Save as PDF" from the browser, or give the two PDF-dependency commands to retry.

Always keep the source `.md` so the PDF can be regenerated once dependencies are present.

## References

- Playwright Python: https://playwright.dev/python/docs/intro

**Analysis only — verify against vendor documentation before applying.**
