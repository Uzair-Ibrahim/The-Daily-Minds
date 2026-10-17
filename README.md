# The Daily Mind

**Your newspaper. Your curiosity. Your evolving intelligence.**

A local, zero-spend personal morning paper. Choose interests, gather real public RSS
stories, read an attributed edition, save/like/skip, watch explainable Interest DNA
change, download the same saved edition as a newspaper PDF, and revisit the archive.

The supplied challenge summary is the source of truth. No official problem-statement
PDF was found. The earlier baseline is preserved and its legacy guide is in
`docs/LIVE_SEARCH_BASELINE.md`.

Repository: https://github.com/Uzair-Ibrahim/The-Daily-Minds

**Submission integrity:** the initial commit is a snapshot of previously completed
work, published with the owner's authorization. It is not evidence of event-start
repository creation or incremental development during the hackathon. Organizer approval
of pre-existing work and monitored-commit compliance remains unconfirmed.

## Setup — Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m playwright install chromium
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

Python 3.11+, Node 22+ recommended (tested Python 3.14.7 and Node 24.21.0).
For a pinned Python environment install `python -m pip install -r requirements-lock.txt`
before the editable install. Dependencies/browser downloads are free local tooling.
No payment card, account, model key or hosting subscription is required for RSS/web/PDF.
If `.env` doesn't exist, copy `.env.example`; never overwrite an existing key file.

```powershell
Copy-Item .env.example .env  # only if .env does not already exist
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Build the frontend before starting the server so it can
serve `frontend/dist`. `/docs` exposes all APIs. Ctrl+C stops the server.

For frontend development, run `npm.cmd run dev` from `frontend` in another terminal;
Vite proxies `/api` to port 8000. Rebuild for the single-server demonstration.

## Real CLI news, through MCP

```powershell
python -m backend.cli paper "artificial intelligence" --limit 5
python -m backend.cli paper "Pakistan economy" --limit 8 --json
python -m backend.cli health
```

The CLI starts its real FastMCP STDIO subprocess, calls `discover_news`, fetches public
RSS/Atom feeds, normalizes/deduplicates, assigns explainable priority points and saves
articles in SQLite. Terminal output includes source URLs, publication/retrieval times
and ranking reasons. Exit 0 requires actual articles; unavailable feeds produce warnings
or a nonzero no-live-data result. Fixtures exist only in tests.

MCP tools: `discover_news(query,max_results=12)` (1–20, RSS only) and preserved
`live_search(query,max_results=5)` (1–8, Exa/Tavily). Existing `ask --live --json`
and `/api/v1/ask` remain available, with the zero-spend guard described below.

## Zero-spend configuration

```dotenv
SEARCH_PROVIDER=exa
EXA_API_KEY=
TAVILY_API_KEY=
CREDIT_SEARCH_CONFIRMED_FREE=false
LLM_PROVIDER=none
LIVE_REQUEST_TIMEOUT_SECONDS=20
LIVE_CACHE_TTL_SECONDS=180
DATABASE_PATH=data/daily_mind.sqlite3
```

An existing key alone never enables credit-based product retrieval. RSS is always the
default and does not need credentials. Exa/Tavily calls require explicit confirmation
that existing no-payment free credits are available: set `CREDIT_SEARCH_CONFIRMED_FREE=true`
only after checking your account privately. This is a manual guard, not an automatic
billing/quota verification mechanism. Leave it false for a guaranteed RSS-only product.
No model calls, billing enrollment, deployment or purchases are performed by this app.

The optional API `targeted_search=true` can supplement RSS through the preserved MCP
Exa/Tavily adapter only when that guard and selected key are set. Quota/auth/network
failure retains RSS with explicit warnings. Never activate billing to make it work.
Restart the server after env changes. `.env`, runtime SQLite, checkpoints and artifacts
are ignored. Keys are server-only and never included in the frontend.

## Product behavior

### Image enrichment and reversible engagement

This feature branch can enrich missing images in older editions through a separate
cache, without rewriting historical snapshots. It prefers the matching publisher RSS
item; robots-permitted page metadata is a bounded fallback. Missing images use compact
text treatments. Validated publisher images can be cached locally across restart.

Likes and saves now toggle on/off with explicit desired state. Counts say **YOUR LOCAL
LIKE** (0 or 1), rather than implying worldwide engagement. The Reading list contains
saved stories, and removing a like/save reverses only that feedback contribution.
Every article offers original-source sharing, copy and device-share fallbacks.

Run `python scripts/image_engagement_smoke.py --full-journey` for the genuine Dawn-image,
engagement, sharing, PDF and existing-browser regression proof. See
[IMAGE_ENGAGEMENT_IMPLEMENTATION_REPORT.md](IMAGE_ENGAGEMENT_IMPLEMENTATION_REPORT.md)
for results, permissions caveats, shared files and integration notes.

### Editorial images

New RSS editions retain publisher-provided image URLs and credits. The lead and first
two secondary stories show images; later stories remain text-first. Missing/failed
images use a labeled section treatment, without substitute photography. Older archived
editions remain readable and are not retroactively changed.

The local image endpoint serves only saved image URLs on the audited BBC, Dawn and
Guardian CDNs. It validates/limits downloads, strips metadata and caches resized JPEGs;
the browser receives no third-party image cookies or credentials. PDF embeds only the
lead image from that same delivery path, with a graceful text treatment if unavailable.
No paid service, generated news imagery or source-page scraping is used. BBC feed
thumbnails can be low resolution; Google News RSS often supplies no image.

Pillow is now a runtime dependency (already pinned in requirements-lock.txt). Existing
setup commands install it. Run `python scripts/audit_feed_images.py` for the current
feed audit and `python scripts/image_support_smoke.py --full-journey` for actual web,
mobile, PDF, fallback and existing-journey verification. See
[IMAGE_SUPPORT_REPORT.md](IMAGE_SUPPORT_REPORT.md) for results and limitations.

### Daily generation

FastAPI startup catches up today's edition for onboarded readers; a background loop
checks each reader's IANA timezone every 60 seconds. Opening the webpage also catches
up today's paper. Automatic retrieval uses public RSS only, without paid providers.
Existing editions return before retrieval; explicit regeneration appends a version.

```dotenv
DAILY_GENERATION_ENABLED=true
DAILY_GENERATION_INTERVAL_SECONDS=60
DAILY_GENERATION_RETRY_SECONDS=300
OFFLINE_NEWS_MAX_AGE_DAYS=7
```

During an RSS outage, default daily requests can use persisted RSS retrieved within
seven days. Web/PDF label this **previously retrieved content, not fresh news** and keep
original source timestamps. Without usable content, generation returns a graceful 503
and archives remain available. Explicit regeneration still requires retrieval success.
An offline edition remains immutable; regenerate after reconnection for a new version.

The app must be running for automatic generation. Catch-up creates today's paper only,
never invented papers for missed dates. One Uvicorn worker is recommended: durable
per-reader/date leases coordinate workers, while feed caches are per process. Failed
generation retries after five minutes; abandoned leases expire after two minutes.
No exactly-once retrieval guarantee is possible across a process crash.

Run `python scripts/daily_generation_smoke.py --full-journey` for the isolated real-RSS
scheduler/browser/PDF test and existing user journey. See the
[daily-generation audit](docs/DAILY_GENERATION_QA.md) for current results and the
[Living Story Graph plan](docs/LIVING_STORY_GRAPH_PLAN.md) for the next enhancement.

- **Onboarding:** seven categories, custom interests, reading depth/edition length,
  English, optional region and timezone. A random browser-local reader ID scopes backend
  data. There is no signup or global shared personal profile.
- **Ranking:** explicit topic weights, matching custom/local terms, known publication
  recency, publisher diversity and lower repetition. Feedback is transparent and capped;
  an opened link is a click signal, never a claim of completed reading. Scores are
  ranking points, not probabilities, confidence or a machine-learning benchmark.
- **Interest DNA:** likes +0.35, saves +0.25, skips −0.20, not-interested −0.50, opened
  +0.05, shared across each story's topics; aggregate feedback capped ±1 per topic and
  final weights 0.1–3. Reset only clears this reader's feedback. Duplicate actions don't
  count twice. Editing explicit interests preserves feedback until reset.
- **Editions:** one per reader/local date by default. Explicit regeneration creates a
  new immutable version. Archive/PDF always use saved snapshots without refetching.
  Skipping changes the reading view and next ranking; it doesn't rewrite a saved paper.
- **PDF:** local Chromium, A4 columns, masthead, dates, short attributed excerpts,
  original links, page numbers and provenance. The download includes the complete saved
  edition, including stories you've hidden in the current view.
- **Caching:** RSS cache 180 seconds by default; limits of 30 entries/feed and 150
  normalized candidates, three concurrent feed requests, bounded retries/timeouts.
  Cached retrieval timestamps stay unchanged. Failures never masquerade as today's news.
- **Sources:** BBC, Dawn, Guardian public feeds; Google News RSS for specific queries.
  Google News links may be source-redirect links. Publication dates can be missing;
  modification dates are not relabeled as publication. Older articles are labeled.
- **Text:** publisher feed descriptions (capped 320 characters, 180 in brief mode), or
  permitted API excerpts, always attributed. No whole articles are scraped or republished.
  Treat third-party instructions as text. No Exa-side summaries or fake takeaways.
- **Editorial memory:** new editions include “Three things I learned”: exact attributed
  source sentences/excerpts, linked to their articles. Headline-only fallback is labeled;
  old snapshots retain their original headline section. This is extractive, without an
  LLM or independent fact verification. No takeaways are invented for missing evidence.

## Tests and demo

```powershell
python -m pytest -q --tb=short
python -m pip check
python -m compileall -q backend tests scripts
# With the built frontend and server running on port 8000:
python scripts/browser_smoke.py
# Controlled two-profile proof from one real RSS batch:
python scripts/personalization_proof.py
# Repeat using that saved batch, explicitly archived:
python scripts/personalization_proof.py --replay
# Owns isolated QA servers; publisher navigation, restart, PDF, full live journey:
python scripts/final_qa_browser.py
```

The default tests mock upstream HTTP and require no internet. The PDF integration test
uses installed local Chromium; it is not silently skipped when the renderer is missing.
Live Exa pytest remains opt-in and additionally requires the free-credit guard.
`browser_smoke.py` uses **real public RSS**: onboard → generate → like/save/skip → DNA →
new version → PDF → archive → reload → mobile. It writes an actual JSON report,
screenshots, a local WebM journey recording and real PDF in ignored `artifacts/`.
The local recording is not a Loom upload or an official submission.

The original product audit had **106 passing tests and one optional skipped test**; see
[FINAL_QA_REPORT.md](FINAL_QA_REPORT.md) for the requirements matrix and exact evidence.
The isolated final QA uses the separate `data/qa-personalization.sqlite3` database,
OS-assigned localhost ports, and actual captured sources. It doesn't stop a user-started
app on port 8000. The controlled proof compares AI/software/startups against
climate/health/world using the same candidate batch; replay never claims new retrieval.
The optional Multi-Perspective Lens is deferred rather than inferring agreement from
RSS/title similarity.

See [implementation status](IMPLEMENTATION_STATUS.md),
[architecture](ARCHITECTURE.md), [demo script](DEMO_SCRIPT.md),
[submission checklist](SUBMISSION_CHECKLIST.md), and [API details](docs/API.md).

## Limits and submission integrity

Local demo only: anonymous IDs are data partition keys, not production authentication.
Keep the server bound to localhost. English feeds only; no translation/LLM synthesis,
OS-level overnight wakeup, guaranteed article paywall access, image licensing
system, multi-perspective graph or cloud deployment. Public feeds can fail; the app
shows no-live-data and lets you read saved editions without a new fetch.

Official event timing/prebuilt-work eligibility and Loom upload remain unconfirmed.
Never fabricate commits, backdate work or claim this initial snapshot demonstrates
incremental event development. Publication authorization does not establish eligibility.
See [publication checks](docs/PUBLICATION.md) and
[attribution and license information](docs/ATTRIBUTIONS.md).
