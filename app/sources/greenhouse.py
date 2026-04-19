"""Greenhouse — public Job Board API.

Greenhouse hosts career pages for many tech companies and exposes each
company board via a free, unauthenticated JSON API:

    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

This source fans out across a curated list of company board tokens, filters
results against the user's keyword/location, and returns unified JobPostings.
No API key is required.
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

NAME = "greenhouse"
LABEL = "Greenhouse public boards (Airbnb, Stripe, Shopify, Databricks, …)"
BASE = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

# Curated list of Greenhouse board tokens for well-known companies.
# Each entry is (board_token, display_name). Most board tokens are the
# lowercased company name; a handful have historical slugs.
GREENHOUSE_BOARDS: tuple[tuple[str, str], ...] = (
    # Travel / marketplace
    ("airbnb", "Airbnb"),
    ("doordash", "DoorDash"),
    ("instacart", "Instacart"),
    ("lyft", "Lyft"),
    ("robinhood", "Robinhood"),
    ("coinbase", "Coinbase"),
    ("shopify", "Shopify"),
    ("reddit", "Reddit"),
    ("pinterest", "Pinterest"),
    ("roblox", "Roblox"),
    ("discord", "Discord"),
    ("figma", "Figma"),
    ("dropbox", "Dropbox"),
    ("duolingo", "Duolingo"),
    # Devtools / cloud
    ("stripe", "Stripe"),
    ("plaid", "Plaid"),
    ("gitlab", "GitLab"),
    ("hashicorp", "HashiCorp"),
    ("mongodb", "MongoDB"),
    ("databricks", "Databricks"),
    ("snowflake", "Snowflake"),
    ("cloudflare", "Cloudflare"),
    ("datadog", "Datadog"),
    ("elastic", "Elastic"),
    ("confluent", "Confluent"),
    ("fastly", "Fastly"),
    ("twilio", "Twilio"),
    ("okta", "Okta"),
    ("splunk", "Splunk"),
    ("pagerduty", "PagerDuty"),
    ("newrelic", "New Relic"),
    ("segmentio", "Segment"),
    ("sentry", "Sentry"),
    ("launchdarkly", "LaunchDarkly"),
    ("auth0", "Auth0"),
    ("algolia", "Algolia"),
    ("benchling", "Benchling"),
    # Productivity / SaaS
    ("asana", "Asana"),
    ("zapier", "Zapier"),
    ("airtable", "Airtable"),
    ("notion", "Notion"),
    ("miro", "Miro"),
    ("canva", "Canva"),
    ("atlassian", "Atlassian"),
    ("gusto", "Gusto"),
    ("squarespace", "Squarespace"),
    ("unity3d", "Unity"),
    ("unityads", "Unity Ads"),
    ("squareinc", "Block (Square)"),
    ("wealthfront", "Wealthfront"),
    ("affirm", "Affirm"),
    ("checkr", "Checkr"),
    ("webflow", "Webflow"),
    ("retool", "Retool"),
    ("vercel", "Vercel"),
    ("nextdoor", "Nextdoor"),
    ("thumbtack", "Thumbtack"),
    ("opensea", "OpenSea"),
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("scaleai", "Scale AI"),
    ("huggingface", "Hugging Face"),
    ("character", "Character.AI"),
    ("perplexity", "Perplexity"),
)


def _fetch_board(client: httpx.Client, board: str) -> list[dict]:
    url = BASE.format(board=board)
    try:
        r = client.get(url, params={"content": "true"}, timeout=httpx.Timeout(10.0))
    except httpx.HTTPError as exc:
        log.debug("greenhouse %s failed: %s", board, exc)
        return []
    if r.status_code != 200:
        log.debug("greenhouse %s returned HTTP %s", board, r.status_code)
        return []
    try:
        data = r.json() or {}
    except ValueError:
        return []
    return data.get("jobs") or []


def _build_posting(
    job: dict,
    *,
    company: str,
    board: str,
    query: str,
    location_terms: set[str],
    remote_only: bool,
) -> JobPosting | None:
    title = (job.get("title") or "").strip()
    if not title:
        return None

    job_location = ""
    loc_obj = job.get("location") or {}
    if isinstance(loc_obj, dict):
        job_location = (loc_obj.get("name") or "").strip()
    elif isinstance(loc_obj, str):
        job_location = loc_obj.strip()

    # Some jobs expose offices[] with more granular location names
    office_names: list[str] = []
    for off in job.get("offices") or []:
        if isinstance(off, dict) and off.get("name"):
            office_names.append(off["name"])
    if office_names and not job_location:
        job_location = ", ".join(office_names)

    description_raw = job.get("content") or ""
    description = truncate(description_raw, 1200)

    is_remote = "remote" in (job_location.lower() + " " + title.lower())
    if remote_only and not is_remote:
        return None

    haystack = " ".join([title, company, description, job_location])
    if query and not matches(haystack, query):
        return None

    if location_terms:
        text = normalize_text(f"{job_location} {description}")
        if not any(term in text for term in location_terms):
            return None

    url = (job.get("absolute_url")
           or f"https://boards.greenhouse.io/{board}/jobs/{job.get('id', '')}")

    posted = (job.get("updated_at") or job.get("first_published")
              or job.get("created_at"))

    tags: list[str] = []
    for dept in job.get("departments") or []:
        if isinstance(dept, dict) and dept.get("name"):
            tags.append(dept["name"])

    return JobPosting(
        id=make_id(NAME, board, str(job.get("id", "")), url),
        title=title,
        company=company,
        location=job_location or None,
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
    boards: Iterable[tuple[str, str]] = GREENHOUSE_BOARDS,
    posted_after_days: int = 30,  # unused by Greenhouse; kept for signature parity
) -> list[JobPosting]:
    location_terms = expand_location_terms(location)
    out: list[JobPosting] = []
    per_board_cap = max(2, (limit or 20) // 4)

    for board, company in boards:
        jobs = _fetch_board(client, board)
        if not jobs:
            continue
        hits_this_board = 0
        for job in jobs:
            posting = _build_posting(
                job,
                company=company,
                board=board,
                query=query,
                location_terms=location_terms,
                remote_only=remote_only,
            )
            if posting is None:
                continue
            out.append(posting)
            hits_this_board += 1
            if hits_this_board >= per_board_cap:
                break
        if len(out) >= (limit or 0) and limit:
            break
    return out[: (limit or len(out))]


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    return search_boards(
        client, query, location, limit, remote_only,
        boards=GREENHOUSE_BOARDS, posted_after_days=posted_after_days,
    )
