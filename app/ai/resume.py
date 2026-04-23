"""AI-driven resume tailoring."""
from __future__ import annotations

import re

from app.ai.client import chat
from app.ai.ats import keyword_overlap
from app.schemas import AICredentials


DEFAULT_FEEDBACK_LOOPS = 10
MAX_FEEDBACK_LOOPS = 10


SYSTEM_PROMPT = """You are an expert technical recruiter and resume writer.
You produce ATS-friendly resumes that are truthful, detailed, and tailored to a specific job.

Hard rules:
- Never fabricate employers, degrees, dates or metrics that are not present in the source material.
- If information is missing, write a clearly-marked placeholder like "[Add metric]" so the candidate can fill it in.
- Use plain Markdown, no tables, no columns, no images, no emojis, no fancy glyphs.
- Follow the user's requested output format exactly when format instructions are provided.
- If no explicit format instructions are given, preserve the source resume's important sections and role history rather than collapsing it into a generic short template.
- Keep all supported employers, titles, dates, major tools, domains, and responsibilities from the source material unless the user explicitly asks to shorten.
- Bullet points under Experience must start with a strong action verb and, where possible, include quantified impact.
- Default to a complete professional resume length that preserves the candidate's detail. Do not force a one-page rewrite.
- Mirror language from the job description naturally where it is supported by the candidate's experience.
- Maximize ATS keyword coverage for the target job, but only using claims, tools, domains, and achievements supported by the candidate source material.
- Ensure the Skills section explicitly includes relevant supported keywords from the job description.
- Rewrite the resume in a polished, professional tone suitable for a strong real-world application.
"""


USER_TEMPLATE = """Target job
-----------
Company: {company}
Title: {job_title}

Job description:
{job_description}

Candidate source material
-------------------------
Existing resume (if any):
{current_resume}

Additional candidate notes (if any):
{candidate_profile}

Requested output format:
{format_instructions}

Produce a tailored resume in Markdown following the rules in the system prompt.
Before writing, make sure you have carried forward all important details from the candidate source material:
- every employer, title, and date range
- all clearly supported technical skills, platforms, and domains
- the strongest responsibilities and achievements from each role

Output ONLY the resume markdown, no preamble, no trailing commentary.
"""


REVISION_TEMPLATE = """You are revising a tailored resume to improve ATS match truthfully.

Target job
-----------
Company: {company}
Title: {job_title}

Job description:
{job_description}

Candidate source material
-------------------------
Existing resume:
{current_resume}

Additional candidate notes:
{candidate_profile}

Requested output format:
{format_instructions}

Current tailored draft
----------------------
{draft_resume}

ATS optimization guidance
-------------------------
Feedback loop iteration: {iteration} of {max_iterations}
Baseline heuristic ATS score from source resume: {baseline_score}
Best heuristic ATS score seen so far: {best_score}
Current draft heuristic ATS score: {draft_score}
Supported JD keywords already present in the candidate source material:
{supported_keywords}

Important supported keywords missing from the current draft that should be added naturally where truthful:
{supported_missing_keywords}

Job-description keywords still missing from the current draft:
{draft_missing_keywords}

Instructions:
- Improve ATS match without fabricating any experience.
- Preserve strong, professional resume writing without dropping important supported source details.
- Add missing supported keywords into Summary, Skills, Experience, or Projects where justified.
- Keep ATS-safe formatting and follow the requested output format.
- If the draft already covers the supported keywords well, tighten phrasing without removing key source content.
- Prefer stronger professional phrasing, clearer prioritization, and more concrete impact statements where the source material supports it.

Output ONLY the revised resume markdown, no commentary.
"""


def _heuristic_score(resume_text: str, job_description: str) -> int:
    _, _, ratio = keyword_overlap(resume_text, job_description)
    return int(round(ratio * 100))


def _format_keyword_list(values: set[str], *, limit: int = 30) -> str:
    items = sorted(values)[:limit]
    if not items:
        return "[none]"
    return ", ".join(items)


def _upsert_skills_keywords(resume_markdown: str, keywords: set[str]) -> str:
    items = [kw for kw in sorted(keywords) if kw]
    if not items:
        return resume_markdown.strip()

    skills_line = ", ".join(items)
    pattern = re.compile(
        r"(?ims)^(#{1,6}\s*skills\s*$|skills\s*$)(.*?)(?=^\s*#{1,6}\s+\w|^\s*[A-Z][A-Za-z /&]+\s*$|\Z)"
    )
    match = pattern.search(resume_markdown)
    if match:
        section = match.group(0)
        if any(kw.lower() in section.lower() for kw in items):
            return resume_markdown.strip()
        updated_section = section.rstrip() + f"\n- Keywords: {skills_line}\n"
        return (resume_markdown[:match.start()] + updated_section + resume_markdown[match.end():]).strip()

    addition = f"\n\nSkills\n- Keywords: {skills_line}\n"
    return (resume_markdown.rstrip() + addition).strip()


def _enforce_supported_keywords(resume_markdown: str, supported_keywords: set[str], job_description: str) -> str:
    draft_keywords, _, _ = keyword_overlap(resume_markdown, job_description)
    missing_supported = supported_keywords - draft_keywords
    if not missing_supported:
        return resume_markdown.strip()
    return _upsert_skills_keywords(resume_markdown, missing_supported)


def generate_resume_markdown(
    creds: AICredentials,
    *,
    job_title: str,
    job_description: str,
    company: str = "",
    current_resume_text: str | None = None,
    candidate_profile: str | None = None,
    format_instructions: str | None = None,
    feedback_loops: int = DEFAULT_FEEDBACK_LOOPS,
) -> str:
    loop_count = max(1, min(int(feedback_loops), MAX_FEEDBACK_LOOPS))
    source_resume = (current_resume_text or "[none provided]").strip()[:12000]
    source_notes = (candidate_profile or "[none provided]").strip()[:4000]
    trimmed_jd = (job_description or "").strip()[:8000]
    requested_format = (format_instructions or "").strip()[:3000] or (
        "Preserve the source resume's section structure and detail level. "
        "Keep all roles, dates, and important points from the uploaded resume."
    )

    user = USER_TEMPLATE.format(
        company=company or "[Unspecified]",
        job_title=job_title,
        job_description=trimmed_jd,
        current_resume=source_resume,
        candidate_profile=source_notes,
        format_instructions=requested_format,
    )
    draft = chat(creds, SYSTEM_PROMPT, user).strip()

    source_material = "\n\n".join(
        part for part in [source_resume, source_notes] if part and part != "[none provided]"
    ).strip()
    baseline_text = source_material or source_resume
    baseline_score = _heuristic_score(baseline_text, trimmed_jd)
    supported_keywords, _, _ = keyword_overlap(baseline_text, trimmed_jd)

    best_resume = draft
    best_score = _heuristic_score(draft, trimmed_jd)
    current_resume = draft
    current_score = best_score

    for iteration in range(1, loop_count + 1):
        current_keywords, current_missing_keywords, _ = keyword_overlap(current_resume, trimmed_jd)
        supported_missing = supported_keywords - current_keywords
        needs_revision = bool(supported_missing) or current_score < baseline_score or iteration == 1
        if not needs_revision:
            break

        revision_user = REVISION_TEMPLATE.format(
            company=company or "[Unspecified]",
            job_title=job_title,
            job_description=trimmed_jd,
            current_resume=source_resume,
            candidate_profile=source_notes,
            format_instructions=requested_format,
            draft_resume=current_resume[:12000],
            iteration=iteration,
            max_iterations=loop_count,
            baseline_score=baseline_score,
            best_score=best_score,
            draft_score=current_score,
            supported_keywords=_format_keyword_list(supported_keywords),
            supported_missing_keywords=_format_keyword_list(supported_missing),
            draft_missing_keywords=_format_keyword_list(current_missing_keywords),
        )
        revised = chat(creds, SYSTEM_PROMPT, revision_user).strip()
        revised = _enforce_supported_keywords(revised, supported_keywords, trimmed_jd)
        revised_score = _heuristic_score(revised, trimmed_jd)
        if revised_score > best_score:
            best_resume = revised
            best_score = revised_score
        current_resume = revised
        current_score = revised_score
        if best_score >= 100:
            break

    best_resume = _enforce_supported_keywords(best_resume, supported_keywords, trimmed_jd)
    best_score = _heuristic_score(best_resume, trimmed_jd)

    # Deterministic safeguard: keep at least the baseline supported keyword coverage
    # while still returning a professionally rewritten resume.
    if best_score < baseline_score and supported_keywords:
        reinforced = _upsert_skills_keywords(best_resume, supported_keywords)
        reinforced_score = _heuristic_score(reinforced, trimmed_jd)
        if reinforced_score >= best_score:
            best_resume = reinforced
            best_score = reinforced_score

    return best_resume
