#!/usr/bin/env python3
"""make_pdf.py - Network Desk PDF whitepaper renderer (Playwright + Chromium).

Dependencies: playwright + markdown2 + the shipped _common.py helpers.
    pip install playwright markdown2 && python -m playwright install chromium

Usage:
    python make_pdf.py --input report.md --specialist vnet-architect
    # --output OPTIONAL -> network-desk/<specialist>/reports/<input-stem>.pdf
    # --outdir <dir>    overrides the base folder (default: network-desk)
    # Cover overrides:  --title --subtitle --classification --version --author

Do NOT switch to xhtml2pdf / reportlab / pdfkit / weasyprint - Chromium is used
for faithful CSS, tables, and emoji handling. Mermaid diagrams are rendered to
PNG up-front by the LOCAL Mermaid CLI (mmdc / npx @mermaid-js/mermaid-cli) via
_common.render_mermaid_blocks and base64-embedded as figures; Chromium itself
does not execute any Mermaid JavaScript and no hosted service is contacted.
Cover page, inline formatting, and emoji stripping mirror make_docx.py.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _common as C  # noqa: E402


BRAND_CSS = """
:root {
  --primary:   #0e5a9c;
  --accent:    #2e7d32;
  --warn:      #d4a017;
  --risk:      #c0392b;
  --stripe:    #f3f7fb;
}
@page {
  size: Letter;
  margin: 0.55in;
  @bottom-center { content: "Network Desk - __SPECIALIST__ - Page " counter(page) " of " counter(pages) " - __DATE__"; font: 9pt 'Calibri', 'Segoe UI', Helvetica, sans-serif; color: #555; }
}
body { font: 10.5pt 'Calibri', 'Segoe UI', Helvetica, Arial, sans-serif; color: #1d1d1f; line-height: 1.45; }
h1 { color: var(--primary); font-size: 22pt; margin: 0 0 6pt; border-bottom: 2pt solid var(--primary); padding-bottom: 4pt; }
h2 { color: var(--primary); font-size: 14pt; margin: 18pt 0 6pt; }
h3 { color: #1f6fb2; font-size: 11.5pt; margin: 12pt 0 4pt; }
a { color: #1f6fb2; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; }
tbody td { padding: 4pt 7pt; border-bottom: 0.5pt solid #ddd; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }
thead th { background: var(--primary); color: white; text-align: left; padding: 5pt 7pt; overflow-wrap: anywhere; word-break: break-word; }
tbody tr:nth-child(even) { background: var(--stripe); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
blockquote { border-left: 3pt solid var(--warn); background: #fff8e1; padding: 6pt 10pt; margin: 8pt 0; }
blockquote.green { border-left-color: var(--accent); background: #e8f5e9; }
blockquote.red { border-left-color: var(--risk); background: #fdecea; }
code, pre { font-family: 'Consolas', 'Menlo', monospace; font-size: 9.5pt; background: #f5f5f7; padding: 1pt 3pt; border-radius: 2pt; }
pre { padding: 6pt 8pt; overflow-x: auto; }
ul, ol { margin: 4pt 0 4pt 18pt; }
.disclaimer { color: #555; font-size: 9pt; border-top: 0.5pt solid #ccc; margin-top: 24pt; padding-top: 6pt; }
"""

HTML_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>__TITLE__</title><style>__CSS__</style></head>
<body>__COVER____BODY____APPENDIX__</body></html>"""


def render_html(md_text, cover, specialist, today, ddir):
    try:
        import markdown2
    except ImportError:
        sys.exit("ERROR: markdown2 not installed. Run: pip install markdown2")

    body = C.decode_entities(md_text)
    body, blocks = C.extract_mermaid_blocks(body)
    body = C.strip_emoji(body)
    replacements, omitted = C.render_mermaid_blocks(blocks, ddir)

    html_body = markdown2.markdown(body, extras=[
        "fenced-code-blocks", "tables", "strike", "task_list", "cuddled-lists",
        "header-ids", "footnotes", "code-friendly",
    ])
    html_body = C.apply_mermaid_replacements(html_body, replacements)

    css = (BRAND_CSS + C.COVER_FIGURE_CSS).replace("__SPECIALIST__", specialist).replace("__DATE__", today)
    page = (HTML_SHELL
            .replace("__TITLE__", C._esc(cover.title))
            .replace("__CSS__", css)
            .replace("__COVER__", C.build_cover_html(cover))
            .replace("__BODY__", html_body)
            .replace("__APPENDIX__", C.appendix_html(omitted)))
    return page, omitted


async def html_to_pdf(html_str, out_path):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        sys.exit("ERROR: playwright not installed. Run: pip install playwright && python -m playwright install chromium")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception as e:
            sys.exit(f"ERROR: could not launch Chromium ({e}). Run: python -m playwright install chromium")
        page = await browser.new_page()
        await page.set_content(html_str, wait_until="networkidle")
        await page.pdf(
            path=str(out_path),
            format="Letter",
            print_background=True,
            margin={"top": "0.55in", "right": "0.55in", "bottom": "0.55in", "left": "0.55in"},
        )
        await browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Network Desk markdown report to PDF.")
    ap.add_argument("--input", required=True, type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path, default=None,
                    help="Output path. If omitted: network-desk/<specialist>/reports/<input-stem>.pdf")
    ap.add_argument("--outdir", default="network-desk",
                    help="Base dir used when --output is omitted (default: network-desk)")
    ap.add_argument("--specialist", default="Network Desk")
    ap.add_argument("--title", default=None, help="Cover title override (else front-matter, else first H1)")
    ap.add_argument("--subtitle", default=None, help="Cover subtitle override")
    ap.add_argument("--classification", default=None, help="Cover classification (e.g. Confidential)")
    ap.add_argument("--version", default=None, help="Cover document version")
    ap.add_argument("--author", default=None, help="Cover author")
    args = ap.parse_args()

    raw = args.input.read_text(encoding="utf-8")
    meta, body = C.parse_front_matter(raw)
    today = datetime.date.today().isoformat()
    cover = C.resolve_cover(meta, args, body, today, args.specialist)
    ddir = C.diagrams_dir(args.specialist, args.outdir)

    page_html, omitted = render_html(body, cover, args.specialist, today, ddir)

    out = C.resolve_output(args.output, args.specialist, args.input.stem, "pdf", args.outdir)
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(html_to_pdf(page_html, out))

    if omitted:
        C.eprint(f"WARNING: {len(omitted)} Mermaid diagram(s) omitted - local Mermaid CLI not found.")
        C.eprint(f"  {C.INSTALL_HINT_MERMAID}")

    size = out.stat().st_size
    print(f"OK  {out}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
