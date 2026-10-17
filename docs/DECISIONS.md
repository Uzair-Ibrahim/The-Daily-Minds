# Decisions

## Current product decisions — The Daily Mind

- Final audit: strict word/phrase custom-interest matches; feedback ranking uses capped
  effective DNA weights; RSS feeds interleave before the candidate cap. These fix actual
  correctness gaps without changing provider/LLM architecture.
- New edition memory uses exact attributed source sentences/excerpts, with labeled
  headline-only fallback. Earlier snapshots remain untouched. No LLM synthesis is implied.
- Multi-Perspective Lens is deferred: title/snippet similarity alone cannot safely prove
  common events, independent reporting or material disagreement.

- Challenge summary is now supplied: build a personal morning paper, with onboarding,
  daily PDF, browser reader, archive, skips and interaction-based adaptation. Original
  problem PDF is unavailable. The internal execution prompt remains local.
- Reuse existing FastAPI/FastMCP/CLI/provider infrastructure. Keep all work local; no
  Git history exists, so do not invent event-start commits or publish before eligibility
  and permission are resolved. A source ZIP checkpoint precedes domain changes.
- RSS/Atom is the ordinary-news path. Exa remains primary for optional targeted semantic
  search, with Tavily selectable; both are gated off unless existing no-payment credits
  are explicitly confirmed. Never spend merely because an API key exists.
- SQLite stdlib provides a small durable store with parameterized SQL/WAL. Anonymous
  browser reader IDs scope profiles/events/archives; no authentication infrastructure.
- Deterministic explainable topic/keyword/recency/diversity/repetition ranking plus
  bounded real feedback is the Interest DNA feature. A click does not mean a read.
- Daily generation is on demand; append explicit regenerated versions. Store complete
  immutable snapshots so web and local Chromium PDF use identical article content.
- React/Vite/Tailwind with local reusable UI components, serif editorial typography,
  system fonts and no licensed image dependency. All important UI controls work.
- Closing takeaways are conservatively labeled “Three things to explore”: actual source
  headlines linked to evidence, not unsupported synthesized conclusions.

## Earlier baseline decisions (historical context)

- SDK integration follows the installed `build-with-exa` skill. Use `AsyncExa.search`
  with highlights only; max_results remains explicit to satisfy our existing 1–8 source
  product limit. No domain, category, date, crawl-age or synthesized-output controls added.
- Latest resolved SDK is exa-py 2.25.0. Its installed API lacks the timeout/HTTP client
  constructor options shown in newer online examples, so pin it and assign the managed
  HTTPX client to `_client`. Response hooks validate status/shape/size before SDK parsing;
  provider code returns redacted errors, controls retries and enforces an overall deadline.
- Caching is now opt-in for reads, bounded to 64 entries in memory. Existing --live
  requests bypass reuse. Failures and expired data are not served. Preserve timestamps
  and label cache hits explicitly. No persistent cache or extra service is introduced.

- Search migration: Exa is primary (`SEARCH_PROVIDER=exa`); Tavily remains explicitly
  selectable. Both implement the same `search(SearchRequest) -> SearchResult` interface.
  The SDK calls Exa's official fixed HTTPS endpoint with inline highlight extraction;
  no extra crawling service, LLM changes or frontend changes are needed.
  Indexed-content caveats are returned as limitations. No automatic provider fallback.

- Official challenge is absent. Build neutral infrastructure only.
- Section 15 explicitly orders FastAPI endpoints along with Phase A. Both reuse one
  orchestrator; routes, controller and service/provider code are separate.
- FastMCP server has exactly one tool. Application retrieval uses a real subprocess
  protocol connection, never a direct provider call. In-memory protocol tests supplement
  real STDIO tests; only test code injects HTTP mocks.
- FastMCP documentation may describe newer releases than the installed release. Verify
  `StdioTransport`, `Client.call_tool`, and `structured_content` against installed APIs.
  Installed FastMCP 3.4.9 requires `FASTMCP_CHECK_FOR_UPDATES=off`, not a boolean;
  the real subprocess test exposed and corrected this version-specific difference.
- No arbitrary upstream URL option; provider URLs are fixed Exa/Tavily HTTPS endpoints. Source links
  are returned as data and never fetched by this baseline.
- LLM implementation remains deferred; the cache follows the bounded policy above.
  LLM configuration is reserved and does not silently enable synthesis.
- No confidence heuristic or fabricated conflict detector. Preserve source excerpts and
  disclose that disagreements and authority have not been automatically verified.
- No agents, authentication, database, frontend, or deployment infrastructure.

## Challenge mini-brief — pending official statement

REAL PROBLEM / TARGET USER: pending

MINIMUM TEST CASE: pending

NAIVE BASELINE: this extractive live-evidence CLI

ONE KILLER FEATURE: pending

WHY IT IS NOVEL RELATIVE TO BASELINE: pending

FIRST DEMO SCENARIO: pending

DOMAIN DATA SOURCE / OFFICIAL API: pending

MEASURABLE SUCCESS CHECK: pending

TOP RISK AND FALLBACK: pending
