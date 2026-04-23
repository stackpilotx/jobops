"""Pydantic request / response models."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ---------- Job search ----------

class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    url: str
    source: str
    posted_at: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    salary: Optional[str] = None
    remote: Optional[bool] = None

    @field_validator("posted_at", mode="before")
    @classmethod
    def coerce_posted_at(cls, value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return str(value)
        return str(value)


class SearchRequest(BaseModel):
    keywords: str = Field(..., description="Free-text query, e.g. 'senior python backend'")
    location: Optional[str] = None
    sources: list[str] = Field(
        default_factory=lambda: [
            # Free aggregators
            "remotive", "arbeitnow", "themuse", "jobicy", "hnhiring",
            # Public ATS boards (many companies per source)
            "greenhouse", "lever", "ashby",
            # Big tech careers APIs
            "google", "amazon", "meta", "apple", "microsoft", "netflix",
            # LinkedIn-backed
            "linkedin",
            "visa", "paypal", "stripe", "adobe", "att", "qualcomm",
            "nike", "adidas", "tmobile", "openai", "claude",
            "nvidia", "intel", "goldmansachs", "oracle",
            "o9", "boeing", "airbnb", "xcom", "twitch", "groww", "zerodha",
            # Bundles
            "fortune500", "india_leaders", "global_tech",
        ]
    )
    # How many jobs to take per source when fanning out the search.
    # Hidden from the UI; keep a sensible server-side default.
    limit_per_source: int = 25
    posted_after: date = Field(default_factory=lambda: date.today() - timedelta(days=30))
    remote_only: bool = False

    @field_validator("posted_after")
    @classmethod
    def validate_posted_after(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("posted_after cannot be in the future")
        return value


class SearchResponse(BaseModel):
    query: str
    total: int
    sources_used: list[str]
    sources_errored: dict[str, str] = Field(default_factory=dict)
    timings_s: dict[str, float] = Field(default_factory=dict)
    jobs: list[JobPosting]


# ---------- AI credentials ----------

class AICredentials(BaseModel):
    provider: str = "openai"  # openai | grok
    api_key: Optional[str] = None  # override server default
    model: Optional[str] = None


# ---------- Resume generation ----------

class ResumeGenerateRequest(BaseModel):
    ai: AICredentials
    job_title: str
    job_description: str
    company: str = ""
    # Any of the following source materials may be provided:
    current_resume_text: Optional[str] = None
    candidate_profile: Optional[str] = None  # free-form "about me"
    format_instructions: Optional[str] = None  # user-requested section order / output shape
    # If provided, the tailored DOCX is built from this uploaded .docx as a
    # styling template (fonts, margins, heading colors, list styles).
    template_docx_base64: Optional[str] = None
    feedback_loops: int = Field(default=10, ge=1, le=10)


class ResumeGenerateResponse(BaseModel):
    resume_markdown: str
    docx_base64: str  # .docx bytes, base64-encoded
    filename: str
    used_template: bool = False  # True when the uploaded DOCX was used as a style template


# ---------- ATS scoring ----------

class ATSRequest(BaseModel):
    ai: AICredentials
    resume_text: str
    job_description: str


class ATSResponse(BaseModel):
    score: int  # 0..100
    matched_keywords: list[str]
    missing_keywords: list[str]
    strengths: list[str]
    gaps: list[str]
    recommendations: list[str]
    formatting_notes: list[str]
