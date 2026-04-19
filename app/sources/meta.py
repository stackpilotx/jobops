"""Meta Careers — scrapes public search page.

The public JSON graphql endpoint at metacareers.com requires dynamic CSRF/doc-id
values. A stable fallback is the public HTML search page, which we parse.
"""
from __future__ import annotations

import json
import re

import httpx

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "meta"
LABEL = "Meta Careers"
SEARCH_URL = "https://www.metacareers.com/jobs"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {"q": query}
    if location:
        params["offices[0]"] = location
    r = client.get(SEARCH_URL, params=params)
    if r.status_code != 200:
        return []
    html = r.text

    # Meta pages embed a JSON blob with job data inside a <script> tag; extract
    # any {"id":"...","title":"...","url":"..."} pattern as a best-effort fallback.
    jobs: list[JobPosting] = []
    for m in re.finditer(
        r'\{[^{}]*"title"\s*:\s*"(?P<title>[^"]+)"[^{}]*"id"\s*:\s*"(?P<id>[A-Za-z0-9_]+)"[^{}]*\}',
        html,
    ):
        title = m.group("title")
        jid = m.group("id")
        if not matches(title, query):
            continue
        url = f"https://www.metacareers.com/jobs/{jid}/"
        jobs.append(JobPosting(
            id=make_id(NAME, jid, url),
            title=title,
            company="Meta",
            location=location,
            url=url,
            source=NAME,
            description=None,
            tags=[],
            remote=None,
        ))
        if len(jobs) >= limit:
            break
    return jobs
