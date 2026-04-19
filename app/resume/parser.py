"""Extract plain text from an uploaded resume (PDF/DOCX/TXT/MD)."""
from __future__ import annotations

import io
from typing import Optional


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
            text = page.extract_text() or ""
            out.append(text)
    return "\n".join(out).strip()


def _parse_docx(data: bytes) -> str:
    import docx2txt
    return (docx2txt.process(io.BytesIO(data)) or "").strip()
