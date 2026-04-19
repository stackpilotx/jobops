"""Remotive — free public job API. https://remotive.com/api-documentation"""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, strip_html, truncate


NAME = "remotive"
LABEL = "Remotive (remote jobs)"
URL = "https://remotive.com/api/remote-jobs"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {"search": query, "limit": max(1, min(limit, 50))}
    r = client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    out: list[JobPosting] = []
    for j in (data.get("jobs") or [])[:limit]:
        out.append(JobPosting(
            id=make_id(NAME, str(j.get("id", "")), j.get("url", "")),
            title=j.get("title", "") or "",
            company=j.get("company_name", "") or "",
            location=j.get("candidate_required_location") or "Remote",
            url=j.get("url", "") or "",
            source=NAME,
            posted_at=j.get("publication_date"),
            description=truncate(j.get("description", "")),
            tags=[t for t in (j.get("tags") or []) if isinstance(t, str)],
            salary=j.get("salary") or None,
            remote=True,
        ))
    return out
