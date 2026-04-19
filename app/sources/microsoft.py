"""Microsoft Careers — public search API."""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, truncate


NAME = "microsoft"
LABEL = "Microsoft Careers"
URL = "https://gcsservices.careers.microsoft.com/search/api/v1/search"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {
        "q": query,
        "l": "en_us",
        "pg": 1,
        "pgSz": max(1, min(limit, 50)),
        "o": "Recent",
        "flt": "true",
    }
    if location:
        params["lc"] = location
    try:
        r = client.get(URL, params=params)
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []

    # response shape: { operationResult: { result: { jobs: [...] } } }
    node = (data.get("operationResult") or {}).get("result") or {}
    jobs_raw = node.get("jobs") or []
    out: list[JobPosting] = []
    for j in jobs_raw[:limit]:
        title = j.get("title") or ""
        jid = str(j.get("jobId") or "")
        url = f"https://jobs.careers.microsoft.com/global/en/job/{jid}"
        locs = j.get("properties", {}).get("locations") or []
        loc = ", ".join([l for l in locs if isinstance(l, str)])
        is_remote = "remote" in loc.lower()
        if remote_only and not is_remote:
            continue
        out.append(JobPosting(
            id=make_id(NAME, jid, url),
            title=title,
            company="Microsoft",
            location=loc or None,
            url=url,
            source=NAME,
            posted_at=j.get("postingDate"),
            description=truncate(j.get("properties", {}).get("description", "")),
            tags=[j.get("properties", {}).get("profession", "")] if j.get("properties", {}).get("profession") else [],
            remote=is_remote,
        ))
    return out
