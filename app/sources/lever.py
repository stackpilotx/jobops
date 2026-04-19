"""Lever — public job board API.

Lever exposes each company's job list at:

    GET https://api.lever.co/v0/postings/{company}?mode=json

This is a free, unauthenticated endpoint. This source fans out across a
curated list of company slugs and filters hits by the user's keywords and
location.
"""
from __future__ import annotations

import logging
from typing import Iterable

import httpx

from app.schemas import JobPosting
from app.sources.base import (
    expand_location_terms,
    make_id,
    matches,
    normalize_text,
    truncate,
)


log = logging.getLogger(__name__)

NAME = "lever"
LABEL = "Lever public boards (Netflix, Ramp, Brex, Eventbrite, …)"
BASE = "https://api.lever.co/v0/postings/{company}"

LEVER_BOARDS: tuple[tuple[str, str], ...] = (
    ("netflix", "Netflix"),
    ("ramp", "Ramp"),
    ("brex", "Brex"),
    ("cruise", "Cruise"),
    ("mozilla", "Mozilla"),
    ("eventbrite", "Eventbrite"),
    ("kickstarter", "Kickstarter"),
    ("quora", "Quora"),
    ("moderna", "Moderna"),
    ("scale", "Scale AI"),
    ("sourcegraph", "Sourcegraph"),
    ("loom", "Loom"),
    ("rippling", "Rippling"),
    ("gopuff", "GoPuff"),
    ("github", "GitHub"),
    ("figma", "Figma"),
    ("anchor", "Anchor"),
    ("attentive", "Attentive"),
    ("zipline", "Zipline"),
    ("palantir", "Palantir"),
    ("palo-alto-networks", "Palo Alto Networks"),
    ("kong", "Kong"),
    ("radix", "Radix Trading"),
    ("upstart", "Upstart"),
    ("peloton", "Peloton"),
    ("thoughtspot", "ThoughtSpot"),
    ("bolt", "Bolt"),
    ("deliveroo", "Deliveroo"),
)


def _fetch_board(client: httpx.Client, company: str) -> list[dict]:
    url = BASE.format(company=company)
    try:
        r = client.get(url, params={"mode": "json"}, timeout=httpx.Timeout(10.0))
    except httpx.HTTPError as exc:
        log.debug("lever %s failed: %s", company, exc)
        return []
    if r.status_code != 200:
        log.debug("lever %s returned HTTP %s", company, r.status_code)
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    if isinstance(data, list):
        return data
    return []


def _build_posting(
    job: dict,
    *,
    company: str,
    slug: str,
    query: str,
    location_terms: set[str],
    remote_only: bool,
) -> JobPosting | None:
    title = (job.get("text") or "").strip()
    if not title:
        return None

    categories = job.get("categories") or {}
    location_name = (categories.get("location") or "").strip()
    commitment = (categories.get("commitment") or "").strip()
    team = (categories.get("team") or "").strip()

    description_text = (
        (job.get("descriptionPlain") or "")
        or (job.get("description") or "")
    )
    description = truncate(description_text, 1200)

    is_remote = "remote" in (location_name.lower() + " " + title.lower())
    if remote_only and not is_remote:
        return None

    haystack = " ".join([title, company, description, location_name, team])
    if query and not matches(haystack, query):
        return None

    if location_terms:
        text = normalize_text(f"{location_name} {description}")
        if not any(term in text for term in location_terms):
            return None

    url = job.get("hostedUrl") or job.get("applyUrl") or ""
    if not url:
        return None

    posted = job.get("createdAt")  # epoch ms

    tags = [t for t in (team, commitment) if t]

    return JobPosting(
        id=make_id(NAME, slug, str(job.get("id", "")), url),
        title=title,
        company=company,
        location=location_name or None,
        url=url,
        source=NAME,
        posted_at=str(posted) if posted else None,
        description=description or None,
        tags=tags[:4],
        remote=(is_remote or None),
    )


def search_boards(
    client: httpx.Client,
    query: str,
    location: str | None,
    limit: int,
    remote_only: bool,
    boards: Iterable[tuple[str, str]] = LEVER_BOARDS,
    posted_after_days: int = 30,
) -> list[JobPosting]:
    location_terms = expand_location_terms(location)
    out: list[JobPosting] = []
    per_board_cap = max(2, (limit or 20) // 4)

    for slug, company in boards:
        jobs = _fetch_board(client, slug)
        if not jobs:
            continue
        hits = 0
        for job in jobs:
            posting = _build_posting(
                job,
                company=company,
                slug=slug,
                query=query,
                location_terms=location_terms,
                remote_only=remote_only,
            )
            if posting is None:
                continue
            out.append(posting)
            hits += 1
            if hits >= per_board_cap:
                break
        if limit and len(out) >= limit:
            break
    return out[: (limit or len(out))]


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    return search_boards(
        client, query, location, limit, remote_only,
        boards=LEVER_BOARDS, posted_after_days=posted_after_days,
    )
