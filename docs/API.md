# API contract

## The Daily Mind product endpoints

Local anonymous reader ID: send a UUID in `X-Reader-ID`. The React app creates and keeps
one in localStorage. This is a localhost data-scoping mechanism, not public authentication.

| Endpoint | Behavior |
|---|---|
| GET /api/topics | Supported categories |
| GET /api/profile | Get/create the current anonymous reader profile |
| PUT /api/profile | Validated topics/weights, keywords, depth, language, locale, length/timezone |
| GET /api/profile/interests | Explainable bounded feedback and effective weights |
| POST /api/profile/reset-feedback | Clear only this reader's events; retain profiles and editions |
| POST /api/editions/generate | `{regenerate:false,targeted_search:false}`; one edition/date, explicit version append |
| GET /api/editions | Reader-scoped archive metadata |
| GET /api/editions/{id} | Immutable snapshot plus separately loaded reader_actions |
| GET /api/editions/{id}/print | Same snapshot as local print HTML; requires reader header |
| GET /api/editions/{id}/pdf | Same snapshot as downloadable local Chromium PDF |
| POST /api/articles/{id}/interactions | `{action:opened|skipped|liked|saved|not_interested}`; idempotent per action/article/reader |

Generation returns HTTP 503 with `no_live_data` when no usable feed results exist and
does not save a fabricated paper. Old editions remain available. PDF failure returns
an actionable 503. Unknown/other-reader edition/article IDs return 404; malformed reader
IDs return 400; invalid profile data returns 422. SQLite failures return redacted 503s.

Snapshots contain normalized URLs, source and feed/provider, short description,
published_at (nullable), retrieved_at, topics, deterministic ranking reasons/components,
profile/DNA at generation, generation time, local date/timezone and immutable version.
Do not refetch source text to render an existing edition or PDF.

New snapshots also contain takeaway_method=extractive_sentences_v1. Each takeaway
references an actual article ID/URL and has kind=source_excerpt or headline_only plus
an evidence limitation. Exact source text is used; no LLM or fact verification implied.
Legacy snapshots may omit these fields and render as the original headline section.

MCP now exposes `discover_news(query,max_results=12)` in addition to `live_search`.
The `paper` CLI calls discover_news over real STDIO and persists retrieved articles.
Credit-based tools require CREDIT_SEARCH_CONFIRMED_FREE=true and the selected key.
The RSS path requires neither. It remains available on optional Exa/Tavily failure.

## Preserved generic evidence API

Start: `uvicorn backend.main:app --host 127.0.0.1`. Interactive schema: `/docs`.

- `GET /health`: local readiness/configuration booleans; no external request.
- `GET /api/v1/capabilities`: selected `search_provider` (`exa` or `tavily`), live search configured, LLM disabled, extractive mode, cache enabled/TTL.
- `POST /api/v1/ask`: same orchestrator and MCP client as CLI.

Request: `{"question":"Python asyncio timeout documentation", "live":true, "max_sources":5}`.
Optional additive field: `use_cache` (default false). True permits a TTL cache hit;
live=true retrieves on a miss; live=false returns no_evidence on a miss. Cache keys
include provider, question and max_sources. Results are held in memory in one app process.
Question is trimmed, length 1–2000; source count is a strict integer 1–8. Unknown fields
are rejected. Invalid input returns HTTP 422. Retrieval failures return HTTP 200 with a
typed status; callers must inspect `status`. There are no automatic external actions.

Response fields:

| Field | Meaning |
|---|---|
| answer | Attributed extractive excerpts, or explicit inability to verify |
| mode | Always `extractive` in this baseline |
| status | `ok`, `partial`, `no_evidence`, `provider_unavailable`, `error` |
| citations | Evidence IDs validated against supplied records |
| evidence | IDs, title, complete HTTP(S) URL, snippet, source_type, UTC retrieval/publication dates, unknown authority, provider relevance score |
| queried_at_utc | Time this search attempt began |
| retrieved_at_utc | Successful provider response time; null on failure/no retrieval |
| freshness | `retrieved_now`, `retrieved_now_publication_date_unknown`, `cached_within_ttl`, or `not_retrieved` |
| limitations | Explicit provenance, missing configuration, upstream failure, and uncertainty notices |
| elapsed_ms | Measured application execution time |

Publication times are used only when the provider supplies a timezone-aware value.
Event times are not supplied by this provider and are not inferred. Empty successful
searches have a retrieval timestamp but no evidence or citations.

Search is selected through server environment configuration, never request parameters.
Exa is primary; Tavily is optional. MCP `live_search` inputs and existing required ask
fields are unchanged; `use_cache` and the cache freshness value are additive.
Exa extracted highlights map to `snippet`, and `publishedDate` maps
to `published_at_utc`. Scores and source authority remain unknown for Exa. A live API
request may retrieve indexed page content; it is not proof of a recent page crawl.
Cached replies retain original retrieval timestamps and carry an explicit cache warning.
