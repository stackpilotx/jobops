"""Extract plain text from an uploaded resume (PDF/DOCX/TXT/MD)."""
from __future__ import annotations

import io
import math
from typing import Any, Optional


def parse_resume_bytes(filename: str, data: bytes) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return _parse_pdf(data)
    if lower.endswith(".docx"):
        return _parse_docx(data)
    if lower.endswith(".doc"):
        # Legacy .doc isn't supported by python-docx; fall back to best-effort decode.
        return data.decode("utf-8", errors="ignore")
    # txt / md / unknown
    return data.decode("utf-8", errors="ignore")


def parse_resume_with_template(filename: str, data: bytes) -> tuple[str, Optional[bytes]]:
    """Return (plain_text, template_docx_bytes | None).

    The template bytes are non-None only when the uploaded file is a .docx —
    those bytes can then be reused by the DOCX generator so the tailored
    resume keeps the same fonts, margins, heading styles and list styles as
    the original upload. For PDF / TXT / MD we can't extract style cleanly,
    so the generator falls back to its default professional styling.
    """
    text = parse_resume_bytes(filename, data)
    lower = (filename or "").lower()
    template_bytes = data if lower.endswith(".docx") else None
    return text, template_bytes


def _parse_pdf(data: bytes) -> str:
    import pdfplumber
    out: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = _parse_pdf_page(page)
            if text:
                out.append(text)
    return "\n\n".join(out).strip()


def _parse_pdf_page(page) -> str:
    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        keep_blank_chars=False,
        use_text_flow=False,
    ) or []
    if not words:
        return (page.extract_text() or "").strip()

    gap = _detect_column_gap(words, page.width, page.height)
    if not gap:
        return _words_to_text(words)

    gap_start, gap_end = gap
    section_heading_tops = [
        float(word["top"])
        for word in words
        if _looks_like_section_heading(str(word.get("text", "")))
    ]
    if section_heading_tops:
        body_top = min(section_heading_tops)
    else:
        body_top = min(float(word["top"]) for word in words if float(word["top"]) >= page.height * 0.12)
    header_words = [word for word in words if float(word["top"]) < body_top]
    body_words = [word for word in words if float(word["top"]) >= body_top]

    left_words = [word for word in body_words if float(word["x1"]) <= gap_start]
    right_words = [word for word in body_words if float(word["x0"]) >= gap_end]
    middle_words = [
        word for word in body_words
        if float(word["x0"]) < gap_end and float(word["x1"]) > gap_start
    ]

    sections = []
    header_text = _words_to_text(header_words)
    if header_text:
        sections.append(header_text)

    middle_text = _words_to_text(middle_words)
    if middle_text:
        sections.append(middle_text)

    sidebar_like = (
        gap_start < page.width * 0.42
        and len(left_words) < len(right_words)
    )
    primary_words = right_words if sidebar_like else left_words
    secondary_words = left_words if sidebar_like else right_words

    primary_text = _words_to_text(primary_words)
    if primary_text:
        sections.append(primary_text)

    secondary_text = _words_to_text(secondary_words)
    if secondary_text:
        sections.append(secondary_text)

    return "\n\n".join(section for section in sections if section).strip()


def _detect_column_gap(words: list[dict[str, Any]], page_width: float, page_height: float) -> tuple[float, float] | None:
    """Detect a large vertical whitespace band that suggests two columns.

    Many resumes use a narrow left sidebar plus a main right column. The
    default PDF text extraction flattens those into a mixed reading order.
    We detect the central whitespace band and then read each column separately.
    """
    if len(words) < 30:
        return None

    body_words = [
        word for word in words
        if page_height * 0.12 <= float(word["top"]) <= page_height * 0.94
    ]
    sample = body_words if len(body_words) >= 20 else words

    bin_width = 6.0
    bin_count = max(1, int(math.ceil(page_width / bin_width)))
    occupied = [False] * bin_count

    for word in sample:
        start = max(0, int(float(word["x0"]) // bin_width))
        end = min(bin_count - 1, int(math.ceil(float(word["x1"]) / bin_width)))
        for idx in range(start, end + 1):
            occupied[idx] = True

    search_start = int(bin_count * 0.18)
    search_end = int(bin_count * 0.82)
    longest: tuple[int, int] | None = None
    run_start: int | None = None

    for idx in range(search_start, search_end):
        if not occupied[idx]:
            if run_start is None:
                run_start = idx
            continue
        if run_start is not None:
            run = (run_start, idx - 1)
            if longest is None or (run[1] - run[0]) > (longest[1] - longest[0]):
                longest = run
            run_start = None

    if run_start is not None:
        run = (run_start, search_end - 1)
        if longest is None or (run[1] - run[0]) > (longest[1] - longest[0]):
            longest = run

    if not longest:
        return None

    gap_start = longest[0] * bin_width
    gap_end = (longest[1] + 1) * bin_width
    gap_width = gap_end - gap_start
    if gap_width < page_width * 0.07:
        return None

    left_count = sum(1 for word in sample if float(word["x1"]) <= gap_start)
    right_count = sum(1 for word in sample if float(word["x0"]) >= gap_end)
    if left_count < 8 or right_count < 8:
        return None

    return (gap_start, gap_end)


def _words_to_text(words: list[dict[str, Any]], y_tolerance: float = 3.5) -> str:
    if not words:
        return ""

    ordered = sorted(words, key=lambda word: (round(float(word["top"]), 1), float(word["x0"])))
    lines: list[list[dict[str, Any]]] = []
    current_line: list[dict[str, Any]] = []
    current_top: float | None = None

    for word in ordered:
        top = float(word["top"])
        if current_line and current_top is not None and abs(top - current_top) > y_tolerance:
            lines.append(current_line)
            current_line = [word]
            current_top = top
            continue
        if not current_line:
            current_line = [word]
            current_top = top
            continue
        current_line.append(word)
        current_top = (current_top + top) / 2 if current_top is not None else top

    if current_line:
        lines.append(current_line)

    rendered_lines: list[str] = []
    for line_words in lines:
        line_words.sort(key=lambda word: float(word["x0"]))
        parts: list[str] = []
        prev_x1: float | None = None
        for word in line_words:
            text = str(word.get("text", "")).strip()
            if not text:
                continue
            x0 = float(word["x0"])
            if prev_x1 is not None and x0 - prev_x1 > 1.5:
                parts.append(" ")
            parts.append(text)
            prev_x1 = float(word["x1"])
        line = "".join(parts).strip()
        if line:
            rendered_lines.append(line)

    return "\n".join(rendered_lines).strip()


def _looks_like_section_heading(text: str) -> bool:
    cleaned = text.strip()
    return (
        len(cleaned) >= 4
        and cleaned.isalpha()
        and cleaned.upper() == cleaned
        and cleaned.lower() != cleaned
    )


def _parse_docx(data: bytes) -> str:
    import docx2txt
    return (docx2txt.process(io.BytesIO(data)) or "").strip()
