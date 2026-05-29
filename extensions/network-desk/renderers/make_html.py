#!/usr/bin/env python3
"""make_html.py - Network Desk standalone HTML renderer.

Install: pip install markdown2
Usage:   python make_html.py --input report.md --specialist "Firewall Engineering"
         # --output is optional; defaults to network-desk/<specialist>/reports/<input-stem>.html
         # override with: --output path/to/report.html  (or --outdir to change the base folder)

Produces a single self-contained .html file (inline CSS, no external links) that
is BOTH viewable in a browser and printable with the same brand styling as the
PDF renderer.
"""
from __future__ import annotations
import argparse, datetime, html, pathlib, re, sys

_ENTITY_RE = re.compile(r"\\?&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,31});")


def decode_entities(text: str) -> str:
    """Normalize HTML entity references in markdown source to their Unicode chars.

    See make_pdf.py for full rationale. Keeps PDF/HTML/DOCX renderers in parity:
    `&mdash;` / `\\&mdash;` / `&amp;mdash;` all become a real em-dash before
    markdown2 sees them, so they never surface literally in the output.
    """
    cur = text
    for _ in range(3):
        new = _ENTITY_RE.sub(lambda m: html.unescape("&" + m.group(1) + ";"), cur)
        if new == cur:
            break
        cur = new
    return cur


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
body { font: 10.5pt 'Segoe UI', Helvetica, Arial, sans-serif; color: #1d1d1f; line-height: 1.5; max-width: 8.5in; margin: 0 auto; padding: 0.55in; }
h1 { color: var(--primary); font-size: 22pt; margin: 0 0 6pt; border-bottom: 2pt solid var(--primary); padding-bottom: 4pt; }
h2 { color: var(--primary); font-size: 14pt; margin: 18pt 0 6pt; }
h3 { color: #2c3e50; font-size: 11.5pt; margin: 12pt 0 4pt; }
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
__BODY__
<p class="footer">Network Desk - __SPECIALIST__ - __DATE__</p>
</body>
</html>"""


def render(md_text: str, specialist: str, today: str) -> str:
    try:
        import markdown2
    except ImportError:
        sys.exit("ERROR: markdown2 not installed. Run: pip install markdown2")
    body = markdown2.markdown(decode_entities(md_text), extras=[
        "fenced-code-blocks", "tables", "strike", "task_list", "cuddled-lists",
        "header-ids", "footnotes", "code-friendly",
    ])
    return (
        HTML_SHELL.replace("__TITLE__", specialist)
        .replace("__CSS__", BRAND_CSS)
        .replace("__BODY__", body)
        .replace("__SPECIALIST__", specialist)
        .replace("__DATE__", today)
    )


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "network-desk"


def resolve_output(output, specialist, stem, ext, outdir):
    """Return the explicit --output, or a structured default:
    <outdir>/<specialist-slug>/reports/<stem>.<ext>."""
    if output is not None:
        return output
    return pathlib.Path(outdir) / _slugify(specialist) / "reports" / f"{stem}.{ext}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Network Desk markdown report to standalone HTML.")
    ap.add_argument("--input", required=True, type=pathlib.Path)
    ap.add_argument("--output", type=pathlib.Path, default=None,
                    help="Output path. If omitted: network-desk/<specialist>/reports/<input-stem>.html")
    ap.add_argument("--outdir", default="network-desk",
                    help="Base dir used when --output is omitted (default: network-desk)")
    ap.add_argument("--specialist", default="Network Desk")
    args = ap.parse_args()

    md_text = args.input.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    page_html = render(md_text, args.specialist, today)

    out = resolve_output(args.output, args.specialist, args.input.stem, "html", args.outdir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page_html, encoding="utf-8")

    size = out.stat().st_size
    print(f"OK  {out}  ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
