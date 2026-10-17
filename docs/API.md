# API contract

## Optional account identity

All private newspaper endpoints accept a verified Supabase bearer access token, or
`X-Reader-ID` for unclaimed guests. A bearer token always determines the reader on
the server; changing reader headers or query parameters cannot switch accounts.
Guest requests to an account-mapped reader return 401, even with auth disabled.
`GET /api/auth/config` exposes only enabled/public provider configuration;
`GET /api/auth/me` requires a valid token and returns its mapped `reader_id`.
Invalid/expired tokens return 401; auth discovery/configuration outages return 503.
Private APIs now use `Cache-Control: no-store` and `Vary: Authorization, X-Reader-ID`.
See [auth configuration](SUPABASE_AUTH.md).

## Image/engagement feature additions

`POST /api/articles/{article_id}/interactions` accepts `active` (default true, preserving
existing clients). `liked` and `saved` may be set false; other actions remain additive.
Responses retain `recorded` and `weights` and add current reader-scoped `engagement`
and the requested `active` state. `engagement.like_count` is a persisted local-reader
0/1 count with `like_count_scope=your_local_reader`, not external social popularity.

`GET /api/reading-list` returns this reader's saved article snapshots and edition IDs.
`GET /api/editions/{id}` adds `article_sections` and `article_engagement` maps, leaving
stored `articles` unchanged. Image metadata does not mutate historical editions:
`GET /api/editions/{id}/articles/{article_id}/image/metadata` returns separately cached
resolution metadata. The existing image-byte endpoint and PDF use that same enrichment.
All these routes require the resolved account or guest reader scope. No arbitrary proxy URL is accepted.

## Editorial image delivery

New article snapshots optionally include `image_url`, `image_origin` and `image_credit`.
Missing fields in older snapshots are supported without migration or refetching.
`GET /api/editions/{edition_id}/articles/{article_id}/image` requires a verified account token or guest `X-Reader-ID`
and resolves only that reader's saved edition/article. It does not accept a URL query.
Returns validated, resized JPEG bytes (200) or an empty unavailable response (204);
invalid reader IDs return 400 and unavailable/inaccessible snapshots return 404.
Responses disable browser caching and use `Vary: Authorization, X-Reader-ID`. The frontend loads a same-origin
blob with its existing reader header and falls back on any failure. Images are optional
and image delivery never changes edition snapshots or reruns discovery.

Remote downloads accept only the exact audited publisher image hosts, public DNS
addresses, valid image formats and bounded sizes/deadlines. Redirects are rejected.
PDF uses the same in-process loader for one lead image, embedded as validated data;
Chromium's external network requests remain blocked. `/print` stays a self-contained
text/section-treatment representation; PDF is the image-bearing print artifact.

## Daily generation semantics

`POST /api/editions/generate` with `{}` returns the latest existing immutable version
for the reader's current IANA-local calendar date, or creates version 1. Startup and
periodic generation use the same service for onboarded readers, with RSS only. Opening
the reader triggers catch-up when the latest saved date is older. Missed days are not
backfilled with newly fetched content. `{ "regenerate": true }` still appends a version
and requires retrieval success, preserving its existing error behavior.

New snapshots include `generation_trigger` (`automatic` or `on_demand`),
`source_retrieved_from` and `source_retrieved_to`. `status=offline_fallback` identifies a
newly assembled paper from persisted RSS, not fresh news. `cached_sources` identifies
short-lived feed-cache reuse. Source publication/retrieval timestamps never change to
the assembly date. Existing legacy snapshots do not require these extra fields.

Generation claims are durable per reader/date. Contention waits boundedly; failure
cooldown or no usable content returns the existing redacted 503 `no_live_data` shape.
SQLite/PDF failures retain their graceful error paths. Configuration and limitations
are documented in README.md and DAILY_GENERATION_QA.md.

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
