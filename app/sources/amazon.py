"""Amazon Jobs — public search JSON endpoint used by amazon.jobs."""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, truncate


NAME = "amazon"
LABEL = "Amazon Jobs"
URL = "https://www.amazon.jobs/en/search.json"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {
        "base_query": query,
        "result_limit": max(1, min(limit, 50)),
        "sort": "recent",
    }
    if location:
        params["loc_query"] = location
    r = client.get(URL, params=params)
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    out: list[JobPosting] = []
    for j in (data.get("jobs") or [])[:limit]:
        title = j.get("title") or ""
        loc = j.get("normalized_location") or j.get("location") or ""
        path = j.get("job_path") or ""
        url = f"https://www.amazon.jobs{path}" if path.startswith("/") else path
        is_remote = "virtual" in (loc.lower()) or "remote" in (loc.lower())
        if remote_only and not is_remote:
            continue
        out.append(JobPosting(
            id=make_id(NAME, str(j.get("id", "")), url),
            title=title,
            company="Amazon",
            location=loc or None,
            url=url,
            source=NAME,
            posted_at=j.get("posted_date"),
            description=truncate(j.get("description_short") or j.get("description", "")),
            tags=[j.get("job_category")] if j.get("job_category") else [],
            salary=None,
            remote=is_remote,
        ))
    return out
