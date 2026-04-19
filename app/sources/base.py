"""Shared helpers for all job sources."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.schemas import JobPosting


def make_id(source: str, *parts: str) -> str:
    raw = "|".join([source, *[p or "" for p in parts]])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return _TAG_RE.sub(" ", s).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def matches(text: str, query: str) -> bool:
    """Cheap relevance filter: every non-trivial query word appears in the text."""
    if not query:
        return True
    text_l = (text or "").lower()
    if "," in query:
        return any(matches(text, part.strip()) for part in query.split(",") if part.strip())
    terms = [t for t in re.split(r"\s+", query.lower().strip()) if len(t) > 1]
    return all(t in text_l for t in terms)


def truncate(text: str, n: int = 1200) -> str:
    t = strip_html(text)
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0] + "..."


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_LOCATION_ALIASES = {
    "bengaluru": {"bengaluru", "bangalore", "bengaluru urban", "blr"},
    "bangalore": {"bangalore", "bengaluru", "bengaluru urban", "blr"},
}


def normalize_text(text: str | None) -> str:
    cleaned = _NON_ALNUM_RE.sub(" ", (text or "").lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def split_locations(location: str | None) -> list[str]:
    if not location:
        return []
    parts = [part.strip() for part in re.split(r"[;,/|]+", location) if part.strip()]
    return parts or ([location.strip()] if location.strip() else [])


def split_keywords(query: str | None) -> list[str]:
    if not query:
        return []
    parts = [part.strip() for part in re.split(r"[;,|]+", query) if part.strip()]
    return parts or ([query.strip()] if query.strip() else [])


def expand_location_terms(location: str | None) -> set[str]:
    normalized = normalize_text(location)
    if not normalized:
        return set()
    terms = {normalized}
    parts = [part.strip() for part in re.split(r"[,/|-]", normalized) if part.strip()]
    terms.update(parts)
    for part in list(terms):
        terms.update(_LOCATION_ALIASES.get(part, set()))
    return {term for term in terms if len(term) >= 2}


def location_matches(location: str | None, *texts: str | None) -> bool:
    locations = split_locations(location)
    if not locations:
        return True
    haystacks = [normalize_text(text) for text in texts if text]
    if not haystacks:
        return False
    return any(
        any(term in hay for hay in haystacks for term in expand_location_terms(single_location))
        for single_location in locations
    )


def company_matches(company: str | None, aliases: Iterable[str]) -> bool:
    normalized_company = normalize_text(company)
    if not normalized_company:
        return False
    normalized_aliases = {normalize_text(alias) for alias in aliases if alias}
    return normalized_company in normalized_aliases
