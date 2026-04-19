"""Ashby — public job board API.

Ashby (popular with modern AI labs and startups) exposes each board at:

    GET https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=false

This source fans out across a curated list of company slugs with NO auth.
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

NAME = "ashby"
LABEL = "Ashby public boards (Linear, PostHog, Vercel, Ramp, …)"
BASE = "https://api.ashbyhq.com/posting-api/job-board/{company}"

ASHBY_BOARDS: tuple[tuple[str, str], ...] = (
    ("linear", "Linear"),
    ("posthog", "PostHog"),
    ("vercel", "Vercel"),
    ("replicate", "Replicate"),
    ("vanta", "Vanta"),
    ("harveyai", "Harvey AI"),
    ("ramp", "Ramp"),
    ("pilot", "Pilot"),
    ("cursor", "Cursor"),
    ("wander", "Wander"),
    ("clay", "Clay"),
    ("grammarly", "Grammarly"),
    ("runway", "Runway"),
    ("modal", "Modal"),
    ("together", "Together AI"),
    ("assembly", "Assembly AI"),
    ("codeium", "Codeium"),
    ("elevenlabs", "ElevenLabs"),
    ("pika", "Pika Labs"),
    ("warp", "Warp"),
    ("supabase", "Supabase"),
    ("neon", "Neon"),
    ("turso", "Turso"),
    ("mercury", "Mercury"),
    ("patreon", "Patreon"),
    ("deeporigin", "Deep Origin"),
)


def _fetch_board(client: httpx.Client, company: str) -> list[dict]:
    url = BASE.format(company=company)
    try:
        r = client.get(
            url,
            params={"includeCompensation": "false"},
            timeout=httpx.Timeout(10.0),
        )
    except httpx.HTTPError as exc:
        log.debug("ashby %s failed: %s", company, exc)
        return []
    if r.status_code != 200:
        log.debug("ashby %s returned HTTP %s", company, r.status_code)
        return []
    try:
        data = r.json() or {}
    except ValueError:
        return []
    # Ashby returns {"jobs": [...]}  (with top-level "title" or "apiVersion")
    return data.get("jobs") or []


def _build_posting(
    job: dict,
    *,
    company: str,
    slug: str,
    query: str,
    location_terms: set[str],
    remote_only: bool,
) -> JobPosting | None:
    title = (job.get("title") or "").strip()
    if not title:
        return None

    location_name = (job.get("location") or "").strip()
    is_remote_flag = bool(job.get("isRemote"))
    if not location_name and job.get("secondaryLocations"):
        location_name = ", ".join(
            l for l in (
                (loc.get("location") if isinstance(loc, dict) else "")
                for loc in job["secondaryLocations"]
            ) if l
        )

    description_text = job.get("descriptionPlain") or job.get("description") or ""
    description = truncate(description_text, 1200)

    department = (job.get("department") or "").strip()
    team = (job.get("team") or "").strip()
    employment = (job.get("employmentType") or "").strip()

    is_remote = is_remote_flag or ("remote" in (location_name.lower() + " " + title.lower()))
    if remote_only and not is_remote:
        return None

    haystack = " ".join([title, company, description, location_name, department, team])
    if query and not matches(haystack, query):
        return None

    if location_terms:
        text = normalize_text(f"{location_name} {description}")
        if not any(term in text for term in location_terms):
            return None

    url = job.get("jobUrl") or job.get("applyUrl") or ""
    if not url:
        return None

    posted = job.get("publishedAt") or job.get("updatedAt")

    tags = [t for t in (department, team, employment) if t]

    return JobPosting(
        id=make_id(NAME, slug, str(job.get("id", "")), url),
        title=title,
        company=company,
        location=location_name or None,
        url=url,
        source=NAME,
        posted_at=posted,
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
    boards: Iterable[tuple[str, str]] = ASHBY_BOARDS,
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
        boards=ASHBY_BOARDS, posted_after_days=posted_after_days,
    )
