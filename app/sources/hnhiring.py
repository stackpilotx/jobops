"""Hacker News — 'Who is hiring' posts indexed by Algolia (no auth)."""
from __future__ import annotations

import re

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "hnhiring"
LABEL = "Hacker News — Who is Hiring"
URL = "https://hn.algolia.com/api/v1/search_by_date"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    # We look for recent comments on Ask HN: Who is hiring threads.
    params = {
        "query": query or "",
        "tags": "comment,story_hiring",
        "hitsPerPage": max(1, min(limit * 3, 60)),
    }
    try:
        r = client.get(URL, params=params)
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json() or {}
    except ValueError:
        return []
    out: list[JobPosting] = []
    for hit in data.get("hits") or []:
        text = hit.get("comment_text") or hit.get("story_text") or ""
        if not text:
            continue
        # Strip HTML
        text_stripped = re.sub(r"<[^>]+>", " ", text)
        text_stripped = re.sub(r"\s+", " ", text_stripped).strip()
        if not text_stripped:
            continue
        if query and not matches(text_stripped, query):
            continue
        # Heuristic: first "sentence" is typically "Company | Role | Location | Remote"
        first = text_stripped.split(". ")[0][:200]
        # Try to split by common delimiters
        parts = re.split(r"\s[|\u2013\u2014\-]\s", first)
        company = parts[0].strip() if parts else "HN Who is Hiring"
        title = parts[1].strip() if len(parts) > 1 else first
        loc_str = ""
        for part in parts[2:]:
            if any(k in part.lower() for k in ("remote", "onsite", "hybrid",
                                               "sf", "nyc", "london", "berlin",
                                               "bengaluru", "bangalore")):
                loc_str = part.strip()
                break
        if remote_only and "remote" not in text_stripped.lower():
            continue
        obj_id = hit.get("objectID") or ""
        url = f"https://news.ycombinator.com/item?id={obj_id}" if obj_id else ""
        if not url:
            continue
        out.append(JobPosting(
            id=make_id(NAME, obj_id),
            title=title[:120],
            company=company[:80] or "HN Who is Hiring",
            location=loc_str or None,
            url=url,
            source=NAME,
            posted_at=hit.get("created_at"),
            description=truncate(text_stripped, 800),
            tags=[],
            remote=("remote" in text_stripped.lower()) or None,
        ))
        if len(out) >= limit:
            break
    return out
