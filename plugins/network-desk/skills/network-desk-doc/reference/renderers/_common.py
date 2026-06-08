#!/usr/bin/env python3
"""_common.py - shared, dependency-free helpers for the Network Desk renderers.

Imports nothing outside the Python standard library so every renderer
(make_docx.py / make_pdf.py / make_html.py) can share one copy of the entity
decoder, output-path resolver, front-matter parser, emoji stripper, cover-page
resolution, and the Mermaid -> PNG bridge.

Mermaid policy: diagrams are rendered ONLY with the local Mermaid CLI
(`mmdc`, falling back to `npx -y @mermaid-js/mermaid-cli`). No hosted/external
service is ever contacted. If the CLI is unavailable the caller emits a
"[diagram omitted]" caption, lists the raw source in an appendix, and prints the
exact install command - it never dumps the source inline.
"""
from __future__ import annotations

import html
import pathlib
import re
import shutil
import subprocess
import sys

# --- Brand / cover constants (shared across renderers) ----------------------
PRIMARY_RGB = (0x0E, 0x5A, 0x9C)   # navy - Title / H1 / table header / accent rule
SECONDARY_RGB = (0x1F, 0x6F, 0xB2)  # blue - H2 / H3 / subtitle
PRIMARY_HEX = "#0e5a9c"
SECONDARY_HEX = "#1f6fb2"

INSTALL_HINT_MERMAID = (
    "npm install -g @mermaid-js/mermaid-cli   "
    "(or run once via: npx -y @mermaid-js/mermaid-cli -i diagram.mmd -o diagram.png)"
)


# --- HTML entity decoding ---------------------------------------------------
# Matches optionally backslash-escaped HTML entity references:
#   &mdash;     -> em-dash
#   \&mdash;    -> em-dash (LLM-escaped form)
#   &amp;mdash; -> em-dash (double-encoded; handled by the stable loop below)
_ENTITY_RE = re.compile(r"\\?&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,31});")


def decode_entities(text: str) -> str:
    """Normalize HTML entity references in markdown source to Unicode chars.

    markdown-it-py / markdown2 treat table-cell content as plain text and do not
    decode named entity references, so without this pre-pass `&mdash;` surfaces
    literally in every output format. Loops because `&amp;mdash;` -> `&mdash;` ->
    em-dash needs more than one pass.
    """
    cur = text
    for _ in range(3):
        new = _ENTITY_RE.sub(lambda m: html.unescape("&" + m.group(1) + ";"), cur)
        if new == cur:
            break
        cur = new
    return cur


# --- Emoji stripping (preserve technical arrows) ----------------------------
# Explicit codepoint ranges for pictographic emoji. We deliberately do NOT use a
# blanket "symbols" sweep so that technical arrows (-> U+2192, => U+21D2, the
# box-drawing set, etc.) survive untouched in network diagrams and prose.
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),  # Misc Symbols & Pictographs, Emoticons, Transport, Supplemental, Symbols & Pictographs Extended-A
    (0x1F000, 0x1F0FF),  # Mahjong/Dominoes/Playing cards
    (0x2600, 0x26FF),    # Misc Symbols (sun, cloud, warning sign, etc.)
    (0x2700, 0x27BF),    # Dingbats (check marks, crosses, stars)
    (0xFE00, 0xFE0F),    # Variation selectors (emoji presentation)
    (0x1F1E6, 0x1F1FF),  # Regional indicator symbols (flags)
)
# Arrows we explicitly keep even though some fall inside symbol blocks.
_ARROW_KEEP = set("\u2190\u2191\u2192\u2193\u2194\u2195\u21D0\u21D2\u21D4\u27A1")
_ZWJ = "\u200d"


def _is_emoji_cp(ch: str) -> bool:
    if ch in _ARROW_KEEP:
        return False
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def strip_emoji(text: str) -> str:
    """Remove emoji codepoints while preserving technical arrows like ->.

    Also drops zero-width joiners and trims the doubled spaces that emoji often
    leave behind (e.g. a leading "warning  Note" heading)."""
    if not text:
        return text
    out = [ch for ch in text if ch != _ZWJ and not _is_emoji_cp(ch)]
    cleaned = "".join(out)
    # Collapse runs of spaces created by removed emoji, and tidy edges.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


# --- Output-path resolution -------------------------------------------------
def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or "network-desk"


# Backwards-compatible alias (renderers historically imported `_slugify`).
_slugify = slugify


def resolve_output(output, specialist, stem, ext, outdir):
    """Return the explicit --output, or a structured default:
    <outdir>/<specialist-slug>/reports/<stem>.<ext>."""
    if output is not None:
        return output
    return pathlib.Path(outdir) / slugify(specialist) / "reports" / f"{stem}.{ext}"


def diagrams_dir(specialist, outdir):
    """Sibling of reports/: <outdir>/<specialist-slug>/diagrams/."""
    return pathlib.Path(outdir) / slugify(specialist) / "diagrams"


# --- YAML front-matter (minimal, flat key: value) ---------------------------
_FM_RE = re.compile(r"^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def parse_front_matter(md_text: str):
    """Split a leading ``---`` YAML-ish block from the body.

    Intentionally minimal: supports a single flat block of ``key: value`` pairs
    (values optionally quoted). Nested structures, lists, and multi-line values
    are not supported - this keeps the renderers dependency-free (no PyYAML).
    Returns ``(meta: dict, body: str)``; ``meta`` is ``{}`` when absent.
    """
    m = _FM_RE.match(md_text)
    if not m:
        return {}, md_text
    meta = {}
    for line in m.group(1).splitlines():
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        if key:
            meta[key] = _unquote(val)
    body = md_text[m.end():]
    return meta, body


# --- Cover-page resolution --------------------------------------------------
def first_h1(body: str) -> str | None:
    """Return the text of the first ATX H1 (``# Title``) in the body, if any."""
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# ") and not s.startswith("## "):
            return strip_emoji(s[2:].strip()) or None
    return None


class Cover:
    """Resolved cover-page fields."""

    __slots__ = ("title", "subtitle", "classification", "version", "author", "date", "specialist")

    def __init__(self, title, subtitle, classification, version, author, date, specialist):
        self.title = title
        self.subtitle = subtitle
        self.classification = classification
        self.version = version
        self.author = author
        self.date = date
        self.specialist = specialist

    def meta_rows(self):
        """(label, value) pairs for the metadata block, omitting empties."""
        rows = []
        if self.classification:
            rows.append(("Classification", self.classification))
        if self.version:
            rows.append(("Version", self.version))
        if self.author:
            rows.append(("Author", self.author))
        if self.date:
            rows.append(("Date", self.date))
        return rows


def _pick(*vals):
    for v in vals:
        if v:
            return v
    return None


def resolve_cover(meta, args, body, today, specialist) -> Cover:
    """Cover precedence: front-matter -> CLI flags -> first H1.

    The ``--specialist`` value is NEVER used as the title; it only labels the
    footer/header. Falls back to the document stem only if nothing else exists.
    """
    fm = lambda *keys: _pick(*[meta.get(k) for k in keys])
    title = _pick(
        fm("title"),
        getattr(args, "title", None),
        first_h1(body),
    ) or "Untitled Report"
    subtitle = _pick(fm("subtitle"), getattr(args, "subtitle", None))
    classification = _pick(fm("classification"), getattr(args, "classification", None))
    version = _pick(fm("version"), getattr(args, "version", None))
    author = _pick(fm("author"), getattr(args, "author", None))
    date = _pick(fm("date"), today)
    return Cover(
        title=strip_emoji(title),
        subtitle=strip_emoji(subtitle) if subtitle else None,
        classification=classification,
        version=version,
        author=author,
        date=date,
        specialist=specialist,
    )


# --- Mermaid -> PNG bridge --------------------------------------------------
def _mmdc_command():
    """Return the argv prefix for the Mermaid CLI, or None if unavailable.

    Prefers a globally installed ``mmdc``; falls back to
    ``npx -y @mermaid-js/mermaid-cli`` when only npx is on PATH.
    """
    mmdc = shutil.which("mmdc")
    if mmdc:
        return [mmdc]
    npx = shutil.which("npx")
    if npx:
        return [npx, "-y", "@mermaid-js/mermaid-cli"]
    return None


def render_mermaid_png(src: str, mmd_path: pathlib.Path, png_path: pathlib.Path) -> bool:
    """Render a Mermaid ``src`` string to ``png_path`` using only the local CLI.

    Writes the ``.mmd`` source alongside the ``.png`` (both under the caller's
    diagrams/ dir). Returns True on success; on any failure (CLI missing,
    non-zero exit, no output produced) returns False so the caller can fall back
    to the "[diagram omitted]" path. Never contacts a hosted service.
    """
    cmd = _mmdc_command()
    if cmd is None:
        return False
    try:
        mmd_path.parent.mkdir(parents=True, exist_ok=True)
        mmd_path.write_text(src, encoding="utf-8")
    except OSError:
        return False
    argv = cmd + ["-i", str(mmd_path), "-o", str(png_path), "-b", "white"]
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    return png_path.exists() and png_path.stat().st_size > 0


def extract_mermaid_blocks(md_text: str):
    """Find fenced ```mermaid blocks. Returns a list of (placeholder, source).

    The caller is responsible for replacing each placeholder in the rendered
    output. Placeholders are unique sentinel strings unlikely to collide with
    document content.
    """
    pattern = re.compile(r"^[ \t]*```+[ \t]*mermaid[ \t]*\r?\n(.*?)\r?\n[ \t]*```+[ \t]*$",
                         re.DOTALL | re.MULTILINE | re.IGNORECASE)
    blocks = []
    counter = {"n": 0}

    def _sub(m):
        counter["n"] += 1
        token = f"\u0000MERMAID_BLOCK_{counter['n']}\u0000"
        blocks.append((token, m.group(1)))
        return token

    replaced = pattern.sub(_sub, md_text)
    return replaced, blocks


def eprint(*a):
    print(*a, file=sys.stderr)


# --- HTML building blocks (shared by make_pdf.py / make_html.py) -------------
import base64 as _base64  # noqa: E402


def _esc(text) -> str:
    return html.escape(str(text), quote=True)


def img_data_uri(png_path: pathlib.Path) -> str:
    """Return a self-contained ``data:image/png;base64,...`` URI for a PNG."""
    data = pathlib.Path(png_path).read_bytes()
    return "data:image/png;base64," + _base64.b64encode(data).decode("ascii")


def build_cover_html(cover) -> str:
    """Render the cover page (title + subtitle + accent rule + metadata)."""
    parts = ['<section class="cover">']
    parts.append(f'<h1 class="cover-title">{_esc(strip_emoji(cover.title))}</h1>')
    if cover.subtitle:
        parts.append(f'<p class="cover-subtitle">{_esc(strip_emoji(cover.subtitle))}</p>')
    parts.append('<div class="accent-rule"></div>')
    rows = cover.meta_rows()
    if rows:
        parts.append('<table class="cover-meta">')
        for label, value in rows:
            parts.append(
                f'<tr><th>{_esc(label)}</th><td>{_esc(strip_emoji(str(value)))}</td></tr>')
        parts.append("</table>")
    parts.append("</section>")
    return "".join(parts)


def figure_block_html(n: int, png_path) -> str:
    """Embedded-PNG figure, or an omitted-diagram caption when png_path is None."""
    if png_path is not None:
        uri = img_data_uri(png_path)
        return (f'<figure class="diagram"><img src="{uri}" alt="Figure {n}">'
                f'<figcaption>Figure {n}.</figcaption></figure>')
    return (f'<figure class="diagram diagram-omitted">'
            f'<figcaption>Figure {n}. [diagram omitted - local Mermaid CLI unavailable]'
            f'</figcaption></figure>')


def appendix_html(omitted) -> str:
    """Appendix listing the raw Mermaid sources that could not be rendered."""
    if not omitted:
        return ""
    parts = ['<section class="appendix"><h1>Appendix: Diagram Sources</h1>',
             "<p>The following Mermaid diagrams could not be rendered because the "
             "local Mermaid CLI was unavailable. Install it and re-run to embed them "
             f"as images:</p><pre class=\"install\">{_esc(INSTALL_HINT_MERMAID)}</pre>"]
    for n, src in omitted:
        parts.append(f"<h3>Figure {n}</h3><pre>{_esc(src)}</pre>")
    parts.append("</section>")
    return "".join(parts)


def render_mermaid_blocks(blocks, ddir):
    """Render extracted ```mermaid blocks to PNGs under ``ddir``.

    ``blocks`` is the (token, source) list from ``extract_mermaid_blocks``.
    Returns ``(replacements, omitted)`` where ``replacements`` maps each token
    to its figure HTML and ``omitted`` is a list of ``(n, source)`` for diagrams
    that could not be rendered (CLI unavailable).
    """
    replacements = {}
    omitted = []
    for idx, (token, src) in enumerate(blocks, start=1):
        stem = f"figure-{idx}"
        mmd = pathlib.Path(ddir) / f"{stem}.mmd"
        png = pathlib.Path(ddir) / f"{stem}.png"
        ok = render_mermaid_png(src, mmd, png)
        if ok:
            replacements[token] = figure_block_html(idx, png)
        else:
            replacements[token] = figure_block_html(idx, None)
            omitted.append((idx, src))
    return replacements, omitted


def apply_mermaid_replacements(html_body: str, replacements) -> str:
    """Swap mermaid placeholder tokens (optionally wrapped in <p>) for figures."""
    for token, fig in replacements.items():
        html_body = re.sub(r"<p>\s*" + re.escape(token) + r"\s*</p>", fig, html_body)
        html_body = html_body.replace(token, fig)
    return html_body


# Shared CSS for cover page, figures, and appendix (appended to each renderer's
# brand stylesheet so PDF and HTML stay visually in parity).
COVER_FIGURE_CSS = """
.cover { text-align: center; margin: 2.2in 0 0; page-break-after: always; }
.cover-title { color: #0e5a9c; font-size: 30pt; border: none; margin: 0 0 8pt; }
.cover-subtitle { color: #1f6fb2; font-size: 16pt; margin: 0 0 14pt; }
.accent-rule { height: 3pt; background: #0e5a9c; width: 60%; margin: 10pt auto 18pt; }
.cover-meta { width: auto; margin: 0 auto; border-collapse: collapse; }
.cover-meta th { background: none; color: #0e5a9c; text-align: right; padding: 2pt 8pt; font-size: 11pt; }
.cover-meta td { text-align: left; padding: 2pt 8pt; border: none; font-size: 11pt; }
figure.diagram { text-align: center; margin: 12pt 0; page-break-inside: avoid; }
figure.diagram img { max-width: 6.3in; height: auto; }
figure.diagram figcaption { font-style: italic; font-size: 9.5pt; color: #555; margin-top: 4pt; }
figure.diagram-omitted figcaption { color: #c0392b; }
.appendix { page-break-before: always; }
.appendix pre, pre.install { background: #f5f5f7; padding: 6pt 8pt; border-radius: 2pt; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 9pt; }
"""
