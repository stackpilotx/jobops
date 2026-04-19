"""LinkedIn — public guest job-search HTML endpoint.

WARNING: LinkedIn's Terms of Service prohibit automated scraping. This module
uses only the publicly-accessible guest search page (no login, no private data),
but you are responsible for respecting robots.txt, rate-limits, and LinkedIn's
ToS. Use sparingly.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from app.schemas import JobPosting
from app.sources.base import company_matches, make_id


NAME = "linkedin"
LABEL = "LinkedIn (public guest search)"
URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"


def search_company(client: httpx.Client, query: str, location: str | None,
                   limit: int, remote_only: bool, aliases: tuple[str, ...],
                   posted_after_days: int = 30) -> list[JobPosting]:
    return search_companies(
        client,
        query,
        location,
        limit,
        remote_only,
        allowed_alias_groups=(aliases,),
        posted_after_days=posted_after_days,
    )


def search_companies(client: httpx.Client, query: str, location: str | None,
                     limit: int, remote_only: bool,
                     allowed_alias_groups: tuple[tuple[str, ...], ...],
                     posted_after_days: int = 30) -> list[JobPosting]:
    params = {
        "keywords": query,
        "location": location or "",
        "start": 0,
        "f_TPR": f"r{max(1, posted_after_days) * 86400}",
    }
    if remote_only:
        params["f_WT"] = 2  # LinkedIn "Remote" work-type code
    try:
        r = client.get(URL, params=params)
    except httpx.HTTPError:
        return []
    if r.status_code != 200 or not r.text.strip():
        return []

    soup = BeautifulSoup(r.text, "lxml")
    cards = soup.select("li, div.base-card")
    out: list[JobPosting] = []
    seen: set[str] = set()
    for card in cards:
        a = card.select_one("a.base-card__full-link, a.job-card-list__title, a[href*='/jobs/view/']")
        if not a:
            continue
        href = (a.get("href") or "").split("?")[0]
        if not href or href in seen:
            continue
        seen.add(href)

        title_el = card.select_one("h3.base-search-card__title")
        title = title_el.get_text(" ", strip=True) if title_el else a.get_text(" ", strip=True)
        company_el = card.select_one("h4.base-search-card__subtitle, a.hidden-nested-link")
        loc_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")

        if not title:
            continue
        company_name = company_el.get_text(" ", strip=True) if company_el else ""
        if allowed_alias_groups and not any(
            company_matches(company_name, alias_group) for alias_group in allowed_alias_groups
        ):
            continue

        out.append(JobPosting(
            id=make_id(NAME, href),
            title=title,
            company=company_name,
            location=loc_el.get_text(" ", strip=True) if loc_el else location,
            url=href,
            source=NAME,
            posted_at=(time_el.get("datetime") if time_el else None),
            description=None,
            tags=[],
            remote=remote_only or None,
        ))
        if len(out) >= limit:
            break
    return out


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    return search_company(
        client,
        query,
        location,
        limit,
        remote_only,
        aliases=(),
        posted_after_days=posted_after_days,
    )
