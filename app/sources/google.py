"""Google Careers — public search endpoint used by careers.google.com."""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, truncate


NAME = "google"
LABEL = "Google Careers"
URL = "https://careers.google.com/api/v3/search/"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {"q": query, "page_size": max(1, min(limit, 50))}
    if location:
        params["location"] = location
    r = client.get(URL, params=params)
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    out: list[JobPosting] = []
    for j in (data.get("jobs") or [])[:limit]:
        title = j.get("title") or j.get("summary", "") or ""
        loc = ", ".join([loc.get("display", "") for loc in (j.get("locations") or []) if loc.get("display")])
        url = j.get("apply_url") or f"https://www.google.com/about/careers/applications/jobs/results/{j.get('id', '')}"
        is_remote = "remote" in loc.lower()
        if remote_only and not is_remote:
            continue
        out.append(JobPosting(
            id=make_id(NAME, str(j.get("id", "")), url),
            title=title,
            company="Google",
            location=loc or None,
            url=url,
            source=NAME,
            posted_at=j.get("publish_date"),
            description=truncate(j.get("description", "") or j.get("summary", "")),
            tags=[c for c in (j.get("categories") or []) if isinstance(c, str)],
            salary=None,
            remote=is_remote,
        ))
    return out
