"""Apple Jobs — public search page scrape."""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

from app.schemas import JobPosting
from app.sources.base import make_id, matches, truncate


NAME = "apple"
LABEL = "Apple Jobs"
SEARCH_URL = "https://jobs.apple.com/en-us/search"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool) -> list[JobPosting]:
    params = {"search": query, "sort": "newest"}
    if location:
        params["location"] = location
    r = client.get(SEARCH_URL, params=params)
    if r.status_code != 200:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    out: list[JobPosting] = []

    for a in soup.select("a[href*='/details/']"):
        href = a.get("href") or ""
        title = a.get_text(" ", strip=True)
        if not title or not matches(title, query):
            continue
        url = href if href.startswith("http") else f"https://jobs.apple.com{href}"
        # Try to grab a location from the surrounding row
        row = a.find_parent("tr") or a.find_parent("li") or a.parent
        loc_text = ""
        if row:
            loc_text = row.get_text(" ", strip=True)[:200]
        out.append(JobPosting(
            id=make_id(NAME, href),
            title=title,
            company="Apple",
            location=loc_text or location,
            url=url,
            source=NAME,
            description=None,
            tags=[],
            remote="remote" in loc_text.lower(),
        ))
        if len(out) >= limit:
            break
    return out
