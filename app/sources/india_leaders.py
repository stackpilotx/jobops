from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.linkedin import search_companies


NAME = "india_leaders"
LABEL = "Top Indian Companies (via LinkedIn guest search)"

INDIA_LEADER_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    # Conglomerates / energy
    ("reliance industries", "reliance", "ril"),
    ("tata group", "tata"),
    ("adani group", "adani"),
    ("larsen toubro", "larsen & toubro", "l&t"),
    # Banks / finance
    ("hdfc bank",),
    ("hdfc", "housing development finance corporation"),
    ("icici bank",),
    ("state bank of india", "sbi"),
    ("axis bank",),
    ("kotak mahindra bank", "kotak"),
    ("bajaj finance",),
    ("bajaj finserv",),
    ("life insurance corporation", "lic", "lic india"),
    # Telecom
    ("bharti airtel", "airtel"),
    ("jio", "reliance jio"),
    # IT services
    ("tata consultancy services", "tcs"),
    ("infosys",),
    ("wipro",),
    ("hcl technologies", "hcltech", "hcl"),
    ("tech mahindra",),
    ("cognizant",),
    ("mindtree",),
    ("ltimindtree",),
    ("persistent systems", "persistent"),
    ("mphasis",),
    ("coforge",),
    # FMCG / consumer
    ("hindustan unilever", "hul"),
    ("itc", "itc limited"),
    ("nestle india",),
    ("asian paints",),
    ("britannia",),
    ("dabur",),
    ("marico",),
    # Auto
    ("maruti suzuki", "maruti"),
    ("tata motors",),
    ("mahindra & mahindra", "mahindra"),
    ("bajaj auto",),
    # Pharma
    ("sun pharmaceutical", "sun pharma"),
    ("dr reddys", "dr reddy's", "dr reddy's laboratories"),
    ("cipla",),
    # New-age / internet
    ("flipkart",),
    ("meesho",),
    ("nykaa",),
    ("zomato",),
    ("swiggy",),
    ("ola", "ola cabs", "ola electric"),
    ("uber india",),
    ("paytm", "one 97 communications"),
    ("phonepe",),
    ("razorpay",),
    ("cred",),
    ("zerodha",),
    ("groww",),
    ("upstox",),
    ("policy bazaar", "policybazaar", "pb fintech"),
    ("dream11", "dream sports"),
    ("byju", "byjus", "byju's"),
    ("unacademy",),
    ("sharechat",),
    ("freshworks",),
    ("zoho",),
    ("postman",),
    ("browserstack",),
    ("chargebee",),
    # Global capability centers (mega hiring in India)
    ("google india",),
    ("microsoft india",),
    ("amazon india",),
    ("walmart labs",),
    ("jpmorgan india",),
    ("goldman sachs india",),
    ("deloitte india",),
    ("accenture india",),
)


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    jobs = search_companies(
        client,
        query,
        location,
        limit,
        remote_only,
        allowed_alias_groups=INDIA_LEADER_ALIAS_GROUPS,
        posted_after_days=posted_after_days,
    )
    return [job.model_copy(update={"source": NAME}) for job in jobs]
