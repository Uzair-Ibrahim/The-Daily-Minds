# The Daily Mind — architecture

Living Story Graph is now implemented in this checkout. It ingests a reader's retrieved
candidate articles before ranking and saves continuing-story evidence in future edition
snapshots. Existing editions are never backfilled or rewritten.

```mermaid
flowchart LR
    RSS[Normalized RSS articles] --> Embed[Lazy local CPU MiniLM embeddings]
    Embed --> Cache[(SQLite embedding cache)]
    RSS --> Hybrid[Conservative headline/entity/number/time gates]
    Embed --> Hybrid
    Hybrid --> Stories[(Reader-scoped clusters and immutable source observations)]
    Stories --> Follow[Explicit reader story follows]
    Follow --> Rank[Bounded ranking bonus and repetition penalty]
    RSS --> Rank
    Rank --> Snapshot[New immutable edition snapshot]
    Stories --> Snapshot
    Snapshot --> Web[React continuing stories]
    Snapshot --> PDF[Matching print HTML and PDF]
    Stories --> API[Reader-scoped detail and follow API]
    API --> Timeline[Expandable accessible timeline]
```

The semantic dependency is optional (`pip install -e ".[stories]"`); download the free
model once with `python scripts/setup_story_model.py`. Runtime uses only cached local
weights and CPU inference, never hosted inference. Model failures retain conservative
deterministic matching. Similarity is a candidate signal, not verification. Distinct
numbers, disjoint headline name cues and publication gaps over 14 days reject matches;
strong lexical overlap can match without a model. Cross-URL connections are labeled
possible, including cases where dates or sufficient source context are missing.

`story_graph.py` owns additive tables with reader scoping, foreign keys and idempotent
content fingerprints. Its candidate history is bounded to 300 recent observations;
detail exposes the latest 150 observations in retrieval chronology. URL membership is
looked up durably outside that candidate bound. Embeddings use normalized vectors,
batched inference and persistent content/model-keyed caching. Edition snapshots retain
at most three continuing stories with three observations each. Follow priority is +1.5,
applies only to new article IDs and is capped to half an edition's boosted slots.
Previously included article IDs from 30 recent editions get a repetition penalty.

Publisher time and original retrieval time remain distinct. Source text differences
are quoted and attributed; the system does not infer factual contradictions, corrections
or event dates. A new observation with sparse evidence explicitly says it cannot
determine what changed. Live timeline/follow state can evolve independently of saved
edition and PDF content.

```mermaid
flowchart TD
    Reader[React reader: onboarding, paper, archive, Interest DNA]
    API[FastAPI routes + newspaper service]
    RSS[Public RSS / Atom feeds + query RSS]
    Tools[FastMCP STDIO: discover_news and live_search]
    Search[Optional Exa SDK / Tavily: explicit free-credit guard]
    Normalize[Plain excerpts, safe URLs, UTC times, dedupe]
    Rank[Explainable relevance, recency, diversity, feedback]
    Memory[Extractive source sentences + labeled headline-only fallback]
    DB[(SQLite local / Postgres cloud: profiles, events, immutable editions)]
    PDF[Local Chromium: shared edition snapshot to print HTML/PDF]
    CLI[CLI paper / ask / health]
    Scheduler[Local startup catch-up and periodic date checks]
    Lease[Reader/date lease and failure cooldown]
    Images[Bounded local publisher-CDN image loader and cache]
    Reader --> API
    Scheduler --> Lease
    API --> Lease
    Lease -->|shared newspaper service| RSS
    CLI --> Tools
    Tools --> RSS
    Tools --> Search
    API --> RSS
    API -->|only optional targeted search| Tools
    RSS --> Normalize
    Search --> Normalize
    Normalize --> Rank
    API --> Rank
    Rank --> DB
    Rank --> Memory
    Memory -->|same saved snapshot| DB
    API <--> DB
    Reader -->|real likes / skips / saves / opened| API
    DB -->|bounded topic feedback| Rank
    DB -->|same immutable snapshot| Reader
    DB --> PDF
    DB -->|saved image URL and credit| Images
    Images -->|reader-scoped JPEG endpoint| Reader
    Images -->|one validated embedded lead image| PDF
    PDF --> Reader
```

The web pipeline calls public RSS directly: MCP is useful for an inspectable discovery
tool and targeted provider connector, not an artificial wrapper around every function.
`paper` CLI really invokes MCP STDIO; optional Exa search does too. Existing typed
`live_search` and `/api/v1/ask` remain functional under the zero-spend guard.

`backend/news/` separates models, ingestion, ranking, storage, service, routes and PDF.
SQLite is accessed with short parameterized transactions and WAL; no destructive
migrations. Reader IDs are random, stored in browser localStorage and passed as
X-Reader-ID. All profile/archive/events queries are scoped to that ID. This is intended
for a localhost demo, not public multi-user authentication.

Edition creation uses a per-reader lock and an atomic SQLite transaction; one saved
version per local date by default, explicit regeneration appends the next version.
Each edition contains complete article/provenance/rendering snapshots and profile/DNA
state. Web and PDF consume these, without independent search at render time. Interaction
topics come from the reader's edition snapshot, not a mutable global article document.

No LLM is needed. Priority points are deterministic, documented heuristic components;
known publication recency never substitutes retrieval time. Bounded feedback shows
observable score/rank changes, while diversity penalties reduce publisher repetition.

Custom interests use bounded phrase matching (AI does not match “said”). The ranking
feedback contribution uses the exact capped effective weights displayed by Interest DNA.
RSS candidate limits interleave feeds to avoid excluding later source categories.

`backend/news/memory.py` extracts actual source sentences/excerpts, prefers publisher
diversity and labels headline-only evidence when descriptions add no substantive text.
It performs no LLM paraphrasing or independent fact verification. Excerpts and evidence
links are saved in the immutable edition; both reader/PDF use the stored text. Legacy
editions retain legacy headline takeaways without migrations or refetching.

`personalization_proof.py` controls both profiles against one real captured RSS batch;
its optional replay is explicitly archived. `final_qa_browser.py` uses an isolated QA
database/server, verifies actual publisher navigation and compares snapshots across
real process restarts on OS-assigned ports. QA shutdown/ownership routes exist only in
scripts/qa_server.py and are ordered before its static mount; they are not production API.

Resource bounds: three RSS requests concurrently, two attempts max, connect/read and
overall per-feed deadlines, byte caps, per-feed/candidate limits, short-lived in-memory
cache. Failed live retrieval doesn't save an invented empty paper. Prior editions stay
readable. Local PDF jobs are serialized; print rendering blocks external requests.

Free-credit status cannot be proven from key presence, so credit search is off by default.
No payment, model, cloud hosting, account scraping or automatic submission workflow exists.

Daily scheduling runs in FastAPI's lifespan and is cancelled on graceful shutdown.
Automatic/manual generation share the service, per-reader lock and durable SQLite
lease. Existing editions return before retrieval. Failed work has a retry cooldown;
abandoned leases expire, and cancellation releases its claim. Bounded per-process
feed caches share responses between query interests and briefly cache feed failures.

Catch-up creates today's local date only. Persisted RSS within the configured maximum
retrieval age can create a labeled offline snapshot. Source times are unchanged; web
and PDF share its status, source-time range and warnings. Existing offline editions are
never silently upgraded. Use one worker for shared feed caching; no jobs run while off.

RSS normalization now extracts an optional best publisher image before stripping HTML
to an attributed description. Metadata survives Article JSON and immutable snapshots;
older editions are unchanged. Only URLs saved in a reader-owned article can reach the
image endpoint. The loader uses exact known publisher CDN hosts, public-address DNS
checks, no redirects or environment proxy, byte/pixel/time/concurrency bounds, verified
raster formats, metadata-free JPEG re-encoding, and bounded coalesced caching. Browser
images use authenticated-by-reader-header same-origin blobs, not third-party requests.
That header is still anonymous local data partitioning, not production authentication.
PDF embeds the validated lead JPEG; its Chromium browser still blocks remote requests.
Only metadata is persistent; in-memory image bytes are best effort and can disappear
on restart. A publisher may change or remove an asset without altering our saved text.

## Deployment storage modes

Local mode retains SQLite. The owner selected Supabase Postgres for durable Render
Free deployment. `DATABASE_BACKEND=postgres` selects a pooled, TLS-verified private
`daily_mind` schema through the existing Store interface; all reader scoping and
immutable snapshots remain unchanged. Transaction-scoped advisory locks preserve
lease/edition/account allocation semantics across connections. App tables are not
exposed through the public Supabase Data API. A missing cloud URL fails closed.
Publisher image cache files remain disposable; source metadata and editions live in
the database. The cloud deployment does not upload existing local private data.
