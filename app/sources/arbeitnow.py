"""Arbeitnow — free public job board API. https://www.arbeitnow.com/api/job-board-api"""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "arbeitnow"
LABEL = "Arbeitnow (EU + remote)"
URL = "https://www.arbeitnow.com/api/job-board-api"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    r = client.get(URL)
    r.raise_for_status()
    data = r.json()
    out: list[JobPosting] = []
    for j in (data.get("data") or []):
        text = " ".join([j.get("title", ""), j.get("description", ""), " ".join(j.get("tags") or [])])
        if not matches(text, query):
            continue
        loc = j.get("location") or ""
        is_remote = bool(j.get("remote"))
        if remote_only and not is_remote:
            continue
        out.append(JobPosting(
            id=make_id(NAME, j.get("slug", ""), j.get("url", "")),
            title=j.get("title", "") or "",
            company=j.get("company_name", "") or "",
            location=loc,
            url=j.get("url", "") or "",
            source=NAME,
            posted_at=j.get("created_at"),
            description=truncate(j.get("description", "")),
            tags=[t for t in (j.get("tags") or []) if isinstance(t, str)],
            salary=None,
            remote=is_remote,
        ))
        if len(out) >= limit:
            break
    return out
