"""Generate a polished, ATS-friendly .docx resume from Markdown.

The Markdown is intentionally simple (headings, paragraphs, bullet lists,
bold/italic) so ATS parsers don't trip over tables, columns or text boxes.
"""
from __future__ import annotations

import io
import re
from typing import Iterable

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches, RGBColor


_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _add_runs_with_inline_formatting(paragraph, text: str) -> None:
    """Split text into runs, applying **bold** and *italic* where present."""
    # Walk text and tokenize
    idx = 0
    # Process bold first
    bold_spans = [(m.start(), m.end(), m.group(1)) for m in _INLINE_BOLD_RE.finditer(text)]
    if not bold_spans:
        _add_italic_runs(paragraph, text)
        return
    pos = 0
    for start, end, inner in bold_spans:
        if start > pos:
            _add_italic_runs(paragraph, text[pos:start])
        run = paragraph.add_run(inner)
        run.bold = True
        pos = end
    if pos < len(text):
        _add_italic_runs(paragraph, text[pos:])


def _add_italic_runs(paragraph, text: str) -> None:
    pos = 0
    for m in _INLINE_ITALIC_RE.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        run = paragraph.add_run(m.group(1))
        run.italic = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def markdown_to_docx(markdown: str, candidate_name: str | None = None) -> bytes:
    doc = Document()

    # Base style
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # Reasonable page margins
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    lines = [ln.rstrip() for ln in (markdown or "").splitlines()]

    # Optional: if the first non-empty line is a header, use it as the name banner
    first_header_used = False

    for raw in lines:
        line = raw.strip()
        if not line:
            # blank line = paragraph break
            continue

        # Headings
        m = _HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if level == 1 and not first_header_used:
                first_header_used = True
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(text)
                run.bold = True
                run.font.size = Pt(20)
                run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
            else:
                p = doc.add_paragraph()
                run = p.add_run(text.upper() if level <= 2 else text)
                run.bold = True
                run.font.size = Pt(13 if level <= 2 else 11)
                run.font.color.rgb = RGBColor(0x0B, 0x3D, 0x91)
                # Add a bottom rule for H1/H2 via paragraph border would require XML;
                # to keep ATS clean we rely on typography alone.
            continue

        # Bullets
        mb = _BULLET_RE.match(raw)
        if mb:
            p = doc.add_paragraph(style="List Bullet")
            _add_runs_with_inline_formatting(p, mb.group(1))
            continue

        # Plain paragraph
        p = doc.add_paragraph()
        _add_runs_with_inline_formatting(p, line)

    # If markdown didn't start with a name heading, and we were given one, prepend it.
    if not first_header_used and candidate_name:
        # Insert at position 0
        p = doc.paragraphs[0].insert_paragraph_before()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(candidate_name)
        run.bold = True
        run.font.size = Pt(20)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Template-based generation: reuse the uploaded .docx's own styles.
# ---------------------------------------------------------------------------

_SECT_PR_TAG = "sectPr"


def _clear_body_keep_styles(doc) -> None:
    """Remove all paragraphs/tables from the body but keep the sectPr + styles."""
    body = doc.element.body
    for child in list(body):
        tag = child.tag.split("}", 1)[-1]
        if tag in ("p", "tbl"):
            body.remove(child)
        # sectPr (page size/margins) stays — python-docx inserts new paragraphs before it.


def _style_exists(doc, name: str) -> bool:
    try:
        doc.styles[name]
        return True
    except KeyError:
        return False


def _add_paragraph_with_style(doc, text: str, style_name: str, *, upper: bool = False):
    """Add a paragraph using the named style if it exists, otherwise fall back
    to bold + sized emphasis on Normal."""
    if _style_exists(doc, style_name):
        p = doc.add_paragraph(style=style_name)
        _add_runs_with_inline_formatting(p, text.upper() if upper else text)
        return p
    # Fallback: bold run with decent size
    p = doc.add_paragraph()
    run = p.add_run(text.upper() if upper else text)
    run.bold = True
    if style_name == "Heading 1":
        run.font.size = Pt(16)
    elif style_name == "Heading 2":
        run.font.size = Pt(13)
    else:
        run.font.size = Pt(11)
    return p


def markdown_to_docx_from_template(
    markdown: str,
    template_bytes: bytes,
    *,
    candidate_name: str | None = None,
) -> bytes:
    """Generate a tailored DOCX that inherits the uploaded resume's styling.

    Strategy:
      1. Open the uploaded DOCX -- this gives us its styles.xml (fonts, colors,
         heading styles, list styles) and sectPr (margins, page size) for free.
      2. Delete the template's body paragraphs / tables but keep sectPr.
      3. Emit new paragraphs using the template's NAMED styles:
         -  "Heading 1" / "Heading 2" / "Heading 3" for # / ## / ###
         -  "List Bullet" for bullet lines
         -  default "Normal" for plain text
      4. If a style is missing, fall back to a sensible bold/size treatment.
    """
    doc = Document(io.BytesIO(template_bytes))
    _clear_body_keep_styles(doc)

    lines = [ln.rstrip() for ln in (markdown or "").splitlines()]
    first_header_used = False

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m = _HEADER_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            style_name = {1: "Heading 1", 2: "Heading 2", 3: "Heading 3"}.get(level, "Heading 3")
            # Level-1 on first occurrence: use as candidate name / banner
            if level == 1 and not first_header_used:
                first_header_used = True
                # If template has a "Title" style, prefer it for the banner
                banner_style = "Title" if _style_exists(doc, "Title") else style_name
                p = _add_paragraph_with_style(doc, text, banner_style)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                # Section headings in uppercase look more professional, but only if
                # the template's heading style doesn't already apply uppercase.
                _add_paragraph_with_style(doc, text, style_name, upper=(level <= 2))
            continue

        mb = _BULLET_RE.match(raw)
        if mb:
            _add_paragraph_with_style(doc, mb.group(1), "List Bullet")
            continue

        # Plain paragraph — uses the template's Normal style automatically.
        p = doc.add_paragraph()
        _add_runs_with_inline_formatting(p, line)

    # Prepend candidate name if markdown had no H1 and we were given one.
    if not first_header_used and candidate_name and doc.paragraphs:
        p = doc.paragraphs[0].insert_paragraph_before()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(candidate_name)
        run.bold = True
        run.font.size = Pt(18)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
