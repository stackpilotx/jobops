"""Jobicy — free public remote-jobs API (no auth).

Docs: https://jobicy.com/api/jobs
"""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "jobicy"
LABEL = "Jobicy (remote jobs worldwide)"
URL = "https://jobicy.com/api/v2/remote-jobs"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {"count": max(1, min(limit, 50))}
    if query:
        params["tag"] = query.split(",")[0].strip()
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
    for j in (data.get("jobs") or [])[: (limit * 3)]:
        title = (j.get("jobTitle") or "").strip()
        company = (j.get("companyName") or "").strip()
        description = truncate(j.get("jobDescription") or "", 1200)
        loc = (j.get("jobGeo") or "Remote").strip()
        url = (j.get("url") or "").strip()
        if not title or not url:
            continue
        haystack = " ".join([title, company, description, loc])
        if query and not matches(haystack, query):
            continue
        out.append(JobPosting(
            id=make_id(NAME, str(j.get("id") or ""), url),
            title=title,
            company=company,
            location=loc or "Remote",
            url=url,
            source=NAME,
            posted_at=j.get("pubDate"),
            description=description or None,
            tags=[t for t in (j.get("jobIndustry") or []) if isinstance(t, str)][:4],
            salary=(j.get("annualSalaryMin") and f"{j.get('annualSalaryMin')}-{j.get('annualSalaryMax')} {j.get('salaryCurrency','USD')}") or None,
            remote=True,
        ))
        if len(out) >= limit:
            break
    return out
