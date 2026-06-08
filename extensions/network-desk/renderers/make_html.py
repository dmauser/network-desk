#!/usr/bin/env python3
"""make_html.py - Network Desk standalone HTML whitepaper renderer.

Dependencies: markdown2 (inline rendering) + the shipped _common.py helpers.
    pip install markdown2

Usage:
    python make_html.py --input report.md --specialist firewall-engineer
    # --output OPTIONAL -> network-desk/<specialist>/reports/<input-stem>.html
    # --outdir <dir>    overrides the base folder (default: network-desk)
    # Cover overrides:  --title --subtitle --classification --version --author

Produces a single self-contained .html file (inline CSS, base64-embedded diagram
images, no external links) that is BOTH viewable in a browser and printable with
the same brand styling as the PDF renderer. Cover page, inline formatting,
Mermaid->PNG figures, and emoji stripping mirror make_docx.py / make_pdf.py.
"""
from __future__ import annotations

import argparse
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
@media print {
  @page { size: Letter; margin: 0.55in; }
}
body { font: 10.5pt 'Calibri', 'Segoe UI', Helvetica, Arial, sans-serif; color: #1d1d1f; line-height: 1.5; max-width: 8.5in; margin: 0 auto; padding: 0.55in; }
h1 { color: var(--primary); font-size: 22pt; margin: 0 0 6pt; border-bottom: 2pt solid var(--primary); padding-bottom: 4pt; }
h2 { color: var(--primary); font-size: 14pt; margin: 18pt 0 6pt; }
h3 { color: #1f6fb2; font-size: 11.5pt; margin: 12pt 0 4pt; }
a { color: #1f6fb2; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0; font-size: 9.5pt; }
thead th { background: var(--primary); color: white; text-align: left; padding: 6pt 8pt; overflow-wrap: anywhere; word-break: break-word; }
tbody td { padding: 5pt 8pt; border-bottom: 0.5pt solid #ddd; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }
tbody tr:nth-child(even) { background: var(--stripe); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
blockquote { border-left: 3pt solid var(--warn); background: #fff8e1; padding: 6pt 10pt; margin: 8pt 0; }
blockquote.green { border-left-color: var(--accent); background: #e8f5e9; }
blockquote.red { border-left-color: var(--risk); background: #fdecea; }
code, pre { font-family: 'Consolas', 'Menlo', monospace; font-size: 9.5pt; background: #f5f5f7; padding: 1pt 3pt; border-radius: 2pt; }
pre { padding: 6pt 8pt; overflow-x: auto; }
.footer { color: #555; font-size: 9pt; border-top: 0.5pt solid #ccc; margin-top: 24pt; padding-top: 6pt; text-align: center; }
"""

HTML_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>__CSS__</style>
</head>
<body>
__COVER__
__BODY__
__APPENDIX__
<p class="footer">Network Desk - __SPECIALIST__ - __DATE__</p>
</body>
</html>"""


def render(md_text, cover, specialist, today, ddir):
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

    css = BRAND_CSS + C.COVER_FIGURE_CSS
    page = (HTML_SHELL
            .replace("__TITLE__", C._esc(cover.title))
            .replace("__CSS__", css)
            .replace("__COVER__", C.build_cover_html(cover))
            .replace("__BODY__", html_body)
            .replace("__APPENDIX__", C.appendix_html(omitted))
            .replace("__SPECIALIST__", C._esc(specialist))
            .replace("__DATE__", C._esc(today)))
    return page, omitted


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Network Desk markdown report to standalone HTML.")
    ap.add_argument("--input", required=True, type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path, default=None,
                    help="Output path. If omitted: network-desk/<specialist>/reports/<input-stem>.html")
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

    page_html, omitted = render(body, cover, args.specialist, today, ddir)

    out = C.resolve_output(args.output, args.specialist, args.input.stem, "html", args.outdir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html, encoding="utf-8")

    if omitted:
        C.eprint(f"WARNING: {len(omitted)} Mermaid diagram(s) omitted - local Mermaid CLI not found.")
        C.eprint(f"  {C.INSTALL_HINT_MERMAID}")

    size = out.stat().st_size
    print(f"OK  {out}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
