"""The Muse — free public API. https://www.themuse.com/developers/api/v2"""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "themuse"
LABEL = "The Muse"
URL = "https://www.themuse.com/api/public/jobs"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    collected: list[JobPosting] = []
    pages_needed = max(1, min(3, (limit // 20) + 1))
    for page in range(pages_needed):
        params = {"page": page, "descending": "true"}
        if location:
            params["location"] = location
        r = client.get(URL, params=params)
        if r.status_code != 200:
            break
        data = r.json()
        for j in data.get("results") or []:
            title = j.get("name", "") or ""
            company = (j.get("company") or {}).get("name", "") or ""
            desc = j.get("contents") or ""
            if not matches(title + " " + desc, query):
                continue
            locs = [l.get("name", "") for l in (j.get("locations") or [])]
            is_remote = any("remote" in (l or "").lower() for l in locs)
            if remote_only and not is_remote:
                continue
            collected.append(JobPosting(
                id=make_id(NAME, str(j.get("id", "")), j.get("refs", {}).get("landing_page", "")),
                title=title,
                company=company,
                location=", ".join(locs) if locs else None,
                url=(j.get("refs") or {}).get("landing_page", "") or "",
                source=NAME,
                posted_at=j.get("publication_date"),
                description=truncate(desc),
                tags=[c.get("name", "") for c in (j.get("categories") or []) if c.get("name")],
                salary=None,
                remote=is_remote,
            ))
            if len(collected) >= limit:
                return collected
    return collected
