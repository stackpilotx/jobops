"""Job sources registry.

Each source module exposes a ``search(client, query, location, limit, remote_only)``
callable returning ``list[JobPosting]`` (invoked inside a worker thread).
"""
from __future__ import annotations

from . import (
    # Free aggregators
    remotive, arbeitnow, themuse, jobicy, hnhiring,
    # Public ATS boards (many companies per source, no auth)
    greenhouse, lever, ashby,
    # Big tech (direct careers API / LinkedIn)
    google, amazon, meta, apple, microsoft, netflix,
    # LinkedIn generic + per-company wrappers
    linkedin,
    visa, paypal, stripe, adobe, att, qualcomm,
    nike, adidas, tmobile, openai, claude,
    nvidia, intel, goldmansachs, oracle,
    o9, boeing, airbnb, xcom, twitch, groww, zerodha,
    # Bundles
    fortune500, india_leaders, global_tech,
)

REGISTRY = {
    # Free public aggregators
    "remotive": remotive,
    "arbeitnow": arbeitnow,
    "themuse": themuse,
    "jobicy": jobicy,
    "hnhiring": hnhiring,
    # Public ATS boards
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    # Big tech direct
    "google": google,
    "amazon": amazon,
    "meta": meta,
    "apple": apple,
    "microsoft": microsoft,
    "netflix": netflix,
    # LinkedIn-backed
    "linkedin": linkedin,
    "visa": visa,
    "paypal": paypal,
    "stripe": stripe,
    "adobe": adobe,
    "att": att,
    "qualcomm": qualcomm,
    "nike": nike,
    "adidas": adidas,
    "tmobile": tmobile,
    "openai": openai,
    "claude": claude,
    "nvidia": nvidia,
    "intel": intel,
    "goldmansachs": goldmansachs,
    "oracle": oracle,
    "o9": o9,
    "boeing": boeing,
    "airbnb": airbnb,
    "xcom": xcom,
    "twitch": twitch,
    "groww": groww,
    "zerodha": zerodha,
    # Bundles
    "fortune500": fortune500,
    "india_leaders": india_leaders,
    "global_tech": global_tech,
}

ALL_SOURCE_KEYS = list(REGISTRY.keys())
