# Job Search AI

AI-assisted job search, resume tailoring, and ATS scoring.

Built with FastAPI + Bulma + Alpine.js + Material Icons. Works with OpenAI **or** Grok
(both use the OpenAI chat-completions protocol; the app just swaps `base_url`).

## Features

- **Keyword search across many sources in parallel**: Google, Amazon, Meta, Apple,
  Microsoft, Netflix careers pages + Remotive + Arbeitnow + The Muse + LinkedIn
  (public guest search).
- **Upload your existing resume** (PDF / DOCX / TXT) — the app parses it to plain text.
- **AI-tailored resume** in professional, ATS-friendly Markdown, exported as `.docx`.
- **ATS score (0–100)** combining deterministic keyword-overlap with an LLM
  qualitative review (strengths, gaps, recommendations, formatting notes).
- Clean Material-inspired UI (Bulma + Alpine + Material Icons).

## Setup (with [uv](https://docs.astral.sh/uv/))

First install `uv` if you don't have it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then set up the project:

```bash
cd job-search-ai
uv sync                   # creates .venv and installs locked deps from pyproject.toml
cp .env.example .env      # then edit .env
```

If you prefer a classic `pip` flow, `requirements.txt` is still provided:
`python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

Edit `.env` — set at least one of:

```
OPENAI_API_KEY=sk-...
GROK_API_KEY=xai-...
```

You can also paste keys at request-time from the UI (AI Settings button in the top
right). Keys pasted in the UI override whatever is in `.env` for that request.

## Run

```bash
uv run python run.py
# or (if a .venv is already active):
python run.py

# then open http://127.0.0.1:8000
```

## How to use

1. Click **AI Settings** (top right), pick provider, paste key if you didn't set one
   in `.env`, save.
2. Type keywords (e.g. `senior python backend`), optionally a location, toggle the
   sources you want, click **Search**.
3. Click any job card → the **Actions for selected job** panel appears below.
4. In that panel:
   - Upload or paste your existing resume.
   - Review (and if needed, expand) the job description.
   - Click **Tailor resume** → AI produces a Markdown resume; click **Download .docx**.
   - Click **Score ATS** → get a 0–100 score plus matched/missing keywords, gaps and
     recommendations. By default the score evaluates the *tailored* resume; if you
     haven't tailored one yet it scores the uploaded resume.

## API endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/api/health` | Shows which keys are configured server-side. |
| GET  | `/api/sources` | Lists available job sources. |
| POST | `/api/search` | `SearchRequest` → aggregated job list. |
| POST | `/api/resume/parse` | Multipart upload → plain-text resume. |
| POST | `/api/resume/generate` | AI-tailored Markdown + base64 `.docx`. |
| POST | `/api/ats/score` | 0–100 score + feedback. |

Try them at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (FastAPI Swagger UI).

## Project layout

```
job-search-ai/
├── run.py                 # uvicorn launcher
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py            # FastAPI app, routes
│   ├── config.py          # settings via pydantic-settings
│   ├── schemas.py         # Pydantic models
│   ├── ai/
│   │   ├── client.py      # unified OpenAI/Grok client
│   │   ├── resume.py      # resume-tailoring prompt
│   │   └── ats.py         # ATS scoring (heuristic + LLM)
│   ├── resume/
│   │   ├── parser.py      # PDF/DOCX → text
│   │   └── generator.py   # Markdown → styled .docx
│   ├── sources/           # one module per job source
│   │   ├── remotive.py  arbeitnow.py  themuse.py
│   │   ├── google.py  amazon.py  meta.py  apple.py
│   │   ├── microsoft.py  netflix.py  linkedin.py
│   │   └── base.py
│   └── static/            # Bulma/Alpine single-page UI
│       ├── index.html
│       ├── css/app.css
│       └── js/app.js
└── data/                  # local scratch (unused by default)
```

## Notes on sources

- **Remotive, Arbeitnow, The Muse** — public, documented JSON APIs. No key needed.
- **Google, Amazon, Microsoft, Netflix** — use the same undocumented-but-public
  JSON endpoints their own careers sites call from the browser. No key needed.
  Fragile: if a company reshapes its API you'll need to update the module.
- **Apple, Meta** — their public pages gate search results behind client-rendered
  HTML; the modules parse the rendered page and will miss jobs that only appear
  after client JS runs. They still work as a best-effort source.
- **LinkedIn** — uses the `jobs-guest/jobs/api/seeMoreJobPostings/search` endpoint,
  which returns rendered HTML without login. **LinkedIn's Terms of Service forbid
  automated scraping.** Even "public guest search" is in a gray zone:
  - Keep request volume low.
  - Don't bypass rate-limits or captchas.
  - Don't attempt to access any data behind login.
  - Don't redistribute scraped content.
  - Your IP may be rate-limited or blocked by LinkedIn at any time.
  - Use at your own risk. For commercial use, pay for the official LinkedIn Jobs
    API or a licensed aggregator (JSearch/Adzuna/etc.) instead.

## Security / privacy

- The UI does **not** persist API keys in `localStorage` — they live in-memory for
  the current tab only. You must re-enter them each session (or set them in `.env`).
- Uploaded resumes and job descriptions are sent to your chosen AI provider for
  the tailor/score endpoints. Check the provider's data-use policy.
- There is no authentication in this app; don't expose it on the public internet
  without adding auth + TLS.

## Roadmap ideas

- Save searches + generated resumes to SQLite.
- Batch "tailor against top N jobs" mode.
- Paid API integrations (Adzuna, JSearch) for better FAANG+Fortune 500 coverage.
- Side-by-side resume diff (original vs tailored).
