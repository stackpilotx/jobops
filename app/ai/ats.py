"""ATS (Applicant Tracking System) scoring.

Combines a deterministic keyword-overlap heuristic with an LLM qualitative review
to produce a single 0-100 score plus actionable feedback.
"""
from __future__ import annotations

import json
import re
from typing import Iterable

from app.ai.client import chat
from app.schemas import AICredentials


_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "we", "you", "they", "he",
    "she", "our", "your", "their", "will", "would", "should", "could", "have",
    "has", "had", "do", "does", "did", "not", "no", "yes", "if", "then", "than",
    "so", "such", "into", "over", "under", "about", "across", "per", "via",
    "any", "all", "each", "some", "many", "few", "most", "more", "less", "very",
    "etc", "including", "include", "includes", "eg", "ie", "job", "role",
    "company", "team", "work", "working", "candidate", "candidates", "experience",
    "experienced", "years", "year",
}


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#\-]{1,}")


def _tokens(text: str) -> list[str]:
    return [m.group(0) for m in _WORD_RE.finditer(text or "")]


def _keywords(text: str, *, min_len: int = 3) -> set[str]:
    out: set[str] = set()
    for tok in _tokens(text):
        low = tok.lower()
        if len(low) < min_len:
            continue
        if low in _STOPWORDS:
            continue
        out.add(low)
    return out


def keyword_overlap(resume_text: str, jd_text: str) -> tuple[set[str], set[str], float]:
    """Return (matched, missing, ratio) for JD keywords found in the resume."""
    resume_kw = _keywords(resume_text)
    jd_kw = _keywords(jd_text)
    if not jd_kw:
        return set(), set(), 0.0
    matched = jd_kw & resume_kw
    missing = jd_kw - resume_kw
    ratio = len(matched) / len(jd_kw)
    return matched, missing, ratio


SYSTEM_PROMPT = """You are an ATS (Applicant Tracking System) auditor.
You evaluate a resume against a job description and return a JSON object with this exact schema:

{
  "score": <integer 0-100, holistic ATS match>,
  "strengths": [<short bullet strings>],
  "gaps": [<short bullet strings describing missing qualifications>],
  "recommendations": [<concrete edits the candidate should make>],
  "formatting_notes": [<ATS-specific formatting issues you noticed, e.g. tables, columns, graphics, unusual fonts; or "none" if clean>]
}

Scoring rubric (be strict):
- 90-100: Strong match on required skills, seniority, domain; resume is ATS-clean.
- 75-89 : Most required skills present, minor gaps.
- 60-74 : Several required items missing or weakly shown.
- 40-59 : Major gaps but some relevant experience.
- 0-39  : Poor match.

Never invent skills the candidate did not claim. Be blunt but constructive."""


def _coerce_string_list(value: object) -> list[str]:
    """Normalize loosely-structured LLM output into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() == "none":
            return []
        return [text]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        items: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if not text or text.lower() == "none":
                continue
            items.append(text)
        return items
    text = str(value).strip()
    if not text or text.lower() == "none":
        return []
    return [text]


def _coerce_score(value: object) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _llm_review(creds: AICredentials, resume_text: str, jd_text: str) -> dict:
    user = (
        "Resume:\n---\n"
        f"{(resume_text or '').strip()[:16000]}\n---\n\n"
        "Job description:\n---\n"
        f"{(jd_text or '').strip()[:8000]}\n---\n\n"
        "Return the JSON object described in the system prompt and nothing else."
    )
    raw = chat(creds, SYSTEM_PROMPT, user, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first {...} block
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {
            "score": 0,
            "strengths": [],
            "gaps": ["AI response could not be parsed."],
            "recommendations": ["Retry the ATS evaluation."],
            "formatting_notes": [],
        }


def score_resume(creds: AICredentials, resume_text: str, jd_text: str) -> dict:
    """Full scoring pipeline combining heuristic + LLM."""
    matched, missing, ratio = keyword_overlap(resume_text, jd_text)
    heuristic_score = int(round(ratio * 100))

    review = _llm_review(creds, resume_text, jd_text)
    llm_score = _coerce_score(review.get("score", 0))

    # Blend: 40% keyword overlap, 60% LLM holistic
    final = int(round(heuristic_score * 0.4 + llm_score * 0.6))
    final = max(0, min(100, final))

    return {
        "score": final,
        "matched_keywords": sorted(list(matched))[:60],
        "missing_keywords": sorted(list(missing))[:60],
        "strengths": _coerce_string_list(review.get("strengths", [])),
        "gaps": _coerce_string_list(review.get("gaps", [])),
        "recommendations": _coerce_string_list(review.get("recommendations", [])),
        "formatting_notes": _coerce_string_list(review.get("formatting_notes", [])),
    }
