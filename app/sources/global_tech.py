"""Global tech companies — Europe + Asia (via LinkedIn guest search)."""
from __future__ import annotations

import httpx

from app.schemas import JobPosting
from app.sources.linkedin import search_companies


NAME = "global_tech"
LABEL = "Global Tech Giants (Spotify, SAP, ByteDance, Canva, …)"

GLOBAL_TECH_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    # Europe — software
    ("spotify",),
    ("klarna",),
    ("revolut",),
    ("wise", "transferwise"),
    ("booking.com", "booking com", "booking holdings"),
    ("adyen",),
    ("mistral ai", "mistral"),
    ("deepl",),
    ("asml",),
    ("arm", "arm holdings"),
    ("prosus", "naspers"),
    ("delivery hero",),
    ("bolt",),
    ("n26",),
    ("gocardless",),
    ("thought machine",),
    ("sap",),
    ("zalando",),
    ("celonis",),
    ("trivago",),
    # China / APAC tech giants
    ("bytedance", "tiktok"),
    ("alibaba",),
    ("tencent",),
    ("baidu",),
    ("xiaomi",),
    ("huawei",),
    ("meituan",),
    ("dji",),
    ("lazada",),
    ("shopee", "sea group"),
    ("grab",),
    ("gojek", "goto"),
    # Australia / NZ
    ("canva",),
    ("atlassian",),
    ("xero",),
    ("afterpay",),
    # Japan / Korea
    ("rakuten",),
    ("line corporation", "line"),
    ("mercari",),
    ("samsung",),
    ("lg",),
    ("naver",),
    ("kakao",),
    ("coupang",),
    # Latam / rest
    ("mercadolibre",),
    ("rappi",),
    ("nubank",),
    ("ifood",),
)


def search(client: httpx.Client, query: str, location: str | None,
           limit: int, remote_only: bool, posted_after_days: int = 30) -> list[JobPosting]:
    jobs = search_companies(
        client,
        query,
        location,
        limit,
        remote_only,
        allowed_alias_groups=GLOBAL_TECH_ALIAS_GROUPS,
        posted_after_days=posted_after_days,
    )
    return [job.model_copy(update={"source": NAME}) for job in jobs]
