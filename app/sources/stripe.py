from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.linkedin import search_company


NAME = "stripe"
LABEL = "Stripe (via LinkedIn guest search)"


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    jobs = search_company(
        client, query, location, limit, remote_only, aliases=("stripe",), posted_after_days=posted_after_days
    )
    return [job.model_copy(update={"source": NAME}) for job in jobs]
