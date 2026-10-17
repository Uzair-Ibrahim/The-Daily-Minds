# The Daily Mind — architecture

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
    DB[(SQLite: profiles, articles, events, immutable editions)]
    PDF[Local Chromium: shared edition snapshot to print HTML/PDF]
    CLI[CLI paper / ask / health]
    Reader --> API
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
