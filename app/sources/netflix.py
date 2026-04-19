"""Netflix Jobs — Phenom-backed public API used by jobs.netflix.com."""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "netflix"
LABEL = "Netflix Jobs"
URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {
        "domain": "netflix.com",
        "query": query,
        "start": 0,
        "num": max(1, min(limit, 50)),
        "sort_by": "new",
    }
    if location:
        params["location"] = location
    r = client.get(URL, params=params)
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    positions = data.get("positions") or data.get("jobs") or []
    out: list[JobPosting] = []
    for j in positions[:limit]:
        title = j.get("name") or j.get("title") or ""
        if not matches(title, query):
            continue
        jid = str(j.get("id") or j.get("job_id") or "")
        url = j.get("canonicalPositionUrl") or j.get("apply_url") or f"https://jobs.netflix.com/jobs/{jid}"
        loc = j.get("location") or ""
        is_remote = "remote" in (loc or "").lower()
        if remote_only and not is_remote:
            continue
        out.append(JobPosting(
            id=make_id(NAME, jid, url),
            title=title,
            company="Netflix",
            location=loc or None,
            url=url,
            source=NAME,
            posted_at=j.get("t_update") or j.get("posted_date"),
            description=truncate(j.get("job_description", "")),
            tags=[j.get("business_unit")] if j.get("business_unit") else [],
            remote=is_remote,
        ))
    return out
