"""FastAPI entrypoint -- routes, static mount, and source orchestration."""
from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai import ats as ats_module
from app.ai import resume as resume_ai
from app.ai.client import AIClientError
from app.config import get_settings
from app.resume.generator import markdown_to_docx, markdown_to_docx_from_template
from app.resume.parser import parse_resume_bytes, parse_resume_with_template
from app.schemas import (
    ATSRequest,
    ATSResponse,
    JobPosting,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
    SearchRequest,
    SearchResponse,
)
from app.sources import ALL_SOURCE_KEYS, REGISTRY
from app.sources.base import location_matches, split_keywords, split_locations


log = logging.getLogger("job-search-ai")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(threadName)s] - %(message)s",
)


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Job Search AI", version="1.0.0")


def _parse_posted_at(value: Any) -> datetime | None:
    """Robustly parse whatever `posted_at` format a source happened to emit.

    Accepts ISO 8601 strings (with or without Z), epoch seconds or epoch
    milliseconds (as int or string), and returns a UTC datetime -- or None
    if the value is missing or unparseable.
    """
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    text = str(value).strip()
    if not text:
        return None

    # Numeric timestamp (epoch seconds or epoch milliseconds)
    if text.lstrip("-").replace(".", "", 1).isdigit():
        try:
            num = float(text)
        except ValueError:
            num = None
        if num is not None:
            # Millisecond vs second detection: > ~year 2286 means it must be ms.
            if num > 10_000_000_000:
                num /= 1000.0
            try:
                return datetime.fromtimestamp(num, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None

    # ISO 8601
    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _posted_after_cutoff(posted_after: date) -> datetime:
    return datetime.combine(posted_after, datetime.min.time(), tzinfo=timezone.utc)


def _posted_after_days(posted_after: date) -> int:
    delta = (date.today() - posted_after).days
    return max(1, delta)


# ---------- UI ----------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------- Meta ----------

@app.get("/api/sources")
async def list_sources() -> dict[str, Any]:
    out = []
    for key in ALL_SOURCE_KEYS:
        mod = REGISTRY[key]
        out.append({"key": key, "label": getattr(mod, "LABEL", key.title())})
    return {"sources": out}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    s = get_settings()
    return {
        "ok": True,
        "openai_key_configured": bool(s.openai_api_key),
        "grok_key_configured": bool(s.grok_api_key),
        "groq_key_configured": bool(s.groq_api_key),
        "anthropic_key_configured": bool(s.anthropic_api_key),
        "gemini_key_configured": bool(s.gemini_api_key),
        "default_provider": s.default_ai_provider,
    }


# ---------- Job search (threaded fan-out) ----------

def _run_source_sync(
    mod, client: httpx.Client, req: SearchRequest, query: str, location: str | None
) -> tuple[str, list[JobPosting] | BaseException, float]:
    """Invoked by each worker thread. Returns (name, jobs-or-exc, elapsed-seconds)."""
    t0 = time.perf_counter()
    try:
        search_kwargs = {
            "client": client,
            "query": query,
            "location": location,
            "limit": req.limit_per_source,
            "remote_only": req.remote_only,
        }
        if "posted_after_days" in inspect.signature(mod.search).parameters:
            search_kwargs["posted_after_days"] = _posted_after_days(req.posted_after)
        jobs = mod.search(**search_kwargs)
        return mod.NAME, jobs, time.perf_counter() - t0
    except Exception as exc:
        return mod.NAME, exc, time.perf_counter() - t0


def _do_parallel_search(
    req: SearchRequest,
) -> tuple[list[JobPosting], dict[str, str], list[str], dict[str, float]]:
    """Blocking: fans each source out to its own thread."""
    settings = get_settings()
    headers = {
        "User-Agent": settings.user_agent,
        "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(settings.request_timeout_s)

    selected = [s for s in req.sources if s in REGISTRY] or ALL_SOURCE_KEYS
    queries = split_keywords(req.keywords) or [req.keywords]
    locations = split_locations(req.location) or [None]

    all_jobs: list[JobPosting] = []
    errors: dict[str, str] = {}
    sources_used: list[str] = []
    timings: dict[str, float] = {}

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=max(4, len(selected)), thread_name_prefix="src") as pool:
            futures = {
                pool.submit(_run_source_sync, REGISTRY[k], client, req, query, location): (k, query, location)
                for k in selected
                for query in queries
                for location in locations
            }
            for fut in as_completed(futures):
                name, outcome, elapsed = fut.result()
                source_key, query, location = futures[fut]
                timing_key = name
                if len(queries) > 1:
                    timing_key = f"{timing_key}:{query}"
                if len(locations) > 1:
                    timing_key = f"{timing_key}:{location}"
                timings[timing_key] = round(elapsed, 3)
                if isinstance(outcome, BaseException):
                    error_key = timing_key
                    errors[error_key] = f"{type(outcome).__name__}: {outcome}"
                    log.warning("Source %s failed in %.2fs: %s", name, elapsed, outcome)
                    continue
                if source_key not in sources_used:
                    sources_used.append(source_key)
                all_jobs.extend(outcome)
                log.info("Source %s returned %d jobs in %.2fs", name, len(outcome), elapsed)

    return all_jobs, errors, sources_used, timings


@app.post("/api/search", response_model=SearchResponse)
async def api_search(req: SearchRequest) -> SearchResponse:
    if not req.keywords.strip():
        raise HTTPException(400, "keywords is required")

    all_jobs, errors, sources_used, timings = await asyncio.to_thread(_do_parallel_search, req)
    cutoff = _posted_after_cutoff(req.posted_after)
    days_window = (date.today() - req.posted_after).days
    # If the user picked a tight window (<= 14 days), drop jobs with no date.
    # For longer windows (30+ days, the default), keep undated jobs since they
    # are likely within the window anyway.
    drop_undated = days_window <= 14

    seen: set[str] = set()
    deduped: list[JobPosting] = []
    dropped_by_date = 0
    dropped_undated = 0
    for j in all_jobs:
        if req.location and not location_matches(req.location, j.location, j.description):
            continue
        posted_at = _parse_posted_at(j.posted_at)
        if posted_at is None:
            if drop_undated:
                dropped_undated += 1
                continue
        elif posted_at < cutoff:
            dropped_by_date += 1
            continue
        key = (j.company + "|" + j.title + "|" + j.url).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(j)

    if dropped_by_date or dropped_undated:
        log.info(
            "Date filter: cutoff=%s, dropped_by_date=%d, dropped_undated=%d, window_days=%d",
            req.posted_after, dropped_by_date, dropped_undated, days_window,
        )

    return SearchResponse(
        query=req.keywords,
        total=len(deduped),
        sources_used=sources_used,
        sources_errored=errors,
        timings_s=timings,
        jobs=deduped,
    )


# ---------- Resume parse ----------

@app.post("/api/resume/parse")
async def api_resume_parse(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        text, template_bytes = parse_resume_with_template(file.filename or "", data)
    except Exception as exc:
        raise HTTPException(400, f"failed to parse resume: {exc}")
    payload: dict[str, Any] = {
        "filename": file.filename,
        "bytes": len(data),
        "text": text,
        "template_docx_base64": None,
        "is_docx_template": False,
    }
    if template_bytes:
        payload["template_docx_base64"] = base64.b64encode(template_bytes).decode("ascii")
        payload["is_docx_template"] = True
    return payload


# ---------- Resume generate ----------

@app.post("/api/resume/generate", response_model=ResumeGenerateResponse)
async def api_resume_generate(req: ResumeGenerateRequest) -> ResumeGenerateResponse:
    try:
        md = resume_ai.generate_resume_markdown(
            req.ai,
            job_title=req.job_title,
            job_description=req.job_description,
            company=req.company,
            current_resume_text=req.current_resume_text,
            candidate_profile=req.candidate_profile,
            format_instructions=req.format_instructions,
            feedback_loops=req.feedback_loops,
        )
    except AIClientError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.exception("resume generation failed")
        raise HTTPException(502, f"AI provider error: {exc}")

    # If the user uploaded a .docx, reuse it as a styling template so the
    # tailored resume keeps the same fonts, margins, heading colors, and
    # list styles.
    used_template = False
    docx_bytes: bytes
    if req.template_docx_base64:
        try:
            template_bytes = base64.b64decode(req.template_docx_base64)
            docx_bytes = markdown_to_docx_from_template(md, template_bytes)
            used_template = True
        except Exception as exc:
            log.warning("template-based DOCX generation failed, falling back: %s", exc)
            docx_bytes = markdown_to_docx(md)
    else:
        docx_bytes = markdown_to_docx(md)

    safe_title = (
        "".join(c for c in req.job_title if c.isalnum() or c in "-_ ")
        .strip()
        .replace(" ", "_")
        or "resume"
    )
    filename = f"resume_{safe_title}.docx"
    return ResumeGenerateResponse(
        resume_markdown=md,
        docx_base64=base64.b64encode(docx_bytes).decode("ascii"),
        filename=filename,
        used_template=used_template,
    )


# ---------- ATS scoring ----------

@app.post("/api/ats/score", response_model=ATSResponse)
async def api_ats_score(req: ATSRequest) -> ATSResponse:
    if not req.resume_text.strip() or not req.job_description.strip():
        raise HTTPException(400, "resume_text and job_description are required")
    try:
        result = ats_module.score_resume(req.ai, req.resume_text, req.job_description)
    except AIClientError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.exception("ats scoring failed")
        raise HTTPException(502, f"AI provider error: {exc}")
    return ATSResponse(**result)


# ---------- Entrypoint ----------

if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)
