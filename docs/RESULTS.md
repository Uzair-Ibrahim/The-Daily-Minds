# Actual verification results

## Current Daily Mind result

The latest product audit is [FINAL_QA_REPORT.md](../FINAL_QA_REPORT.md): **106 passed,
1 skipped**, actual two-profile RSS proof, verified publisher navigation, real server
restart comparison, attributed editorial memory and 3-page final QA PDF. Earlier counts
and sample page lengths below belong to the first implementation.

See [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) for the current product:
**99 passed, 1 skipped**, real RSS CLI/browser paths, actual two-page PDF, feedback-driven
ranking-order changes and local recording. Exa/Tavily were not called during the
zero-spend product build. The reports below are historical baseline SDK verification
from before that guard was introduced.

## Historical result: official Exa SDK and cache integration

Verified on 2026-10-17 (Asia/Karachi), using the installed
[`build-with-exa` skill](../.agents/skills/build-with-exa/SKILL.md) and its SDK/search
references. Installed the latest resolved official SDK, **exa-py 2.25.0**, and pinned it
in pyproject.toml and requirements-lock.txt. The lock now records 85 dependency versions.
No credentials were printed or written to source/docs. The existing `.env` supplies the key.

| Command/check | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pip install exa-py` / editable project refresh | Succeeded with approved network access; initial sandbox download was blocked |
| `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | **83 passed, 1 skipped in 60.54s**, zero failures; live test remains opt-in |
| `.\.venv\Scripts\python.exe scripts/smoke_live.py` | **LIVE_SMOKE_TEST: PASS**, exit 0, 4861 ms; retrieved at `2026-10-17T07:06:17.765520Z` |
| Actual `python -m backend.cli ask "What does Python documentation say about asyncio timeout?" --live --json --max-sources 2` | **Exit 0, status ok**, two real evidence records and citations, retrieval time `2026-10-17T07:06:48.618974Z` |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements found |
| `.\.venv\Scripts\python.exe -m compileall -q backend tests scripts` | Exit 0 |

Real CLI sources returned:

- https://docs.python.org/3/library/asyncio-task.html
- https://docs.python.org/release/3.11.0/library/asyncio-task.html

Both had actual highlight content, bounded to 3000 characters. Publication dates were
unknown; freshness was `retrieved_now_publication_date_unknown`. These results prove
live API connectivity, not that source pages were newly crawled or all claims verified.

Implementation retains FastAPI routes, MCP `live_search(query,max_results)`, CLI `ask`
and extractive synthesis. The provider now calls `AsyncExa.search`, with highlights only
as the skill recommends. The existing 1–8 result bound justifies an explicit SDK
num_results argument. No domain/category/publication filters or generated synthesis added.
Tavily remains available through SEARCH_PROVIDER=tavily; there is no silent fallback.

New tests verify SDK invocation, HTTP client closure, connection retry recovery,
response validation, TTL expiry, cache capacity, mutation isolation, failed-result
exclusion, explicit cache opt-in, default fresh-query bypass, offline cache misses and
Windows Unicode JSON output. Existing real STDIO tests still cover both search adapters.

An initial SDK live smoke retrieved data but encountered a Windows cp1252 Unicode
printing error. JSON output now uses ASCII escaping and normal CLI output uses UTF-8;
two regression tests and the successful smoke/actual CLI reruns verify the fix.

Cache is bounded and process-local, TTL 180 seconds by default. Reads require
use_cache=true (or CLI --cache); ordinary --live calls remain fresh. Cache hits preserve
original retrieval timestamps and use freshness=cached_within_ttl. Separate CLI
invocations start with an empty cache. Failures and expired entries are not served.

Known compatibility limit: SDK 2.25.0 exposes no public timeout/client injection API;
the adapter sets its managed HTTPX client via the pinned `_client` hook. Upgrades must
retest this hook. No LLM or frontend changes were made. The full suite's one skipped
test is the opt-in live pytest test; real connectivity was independently verified by
the smoke command and actual CLI run above.

## Historical result: Exa HTTP provider migration

Verified 2026-10-17 (Asia/Karachi). Exa is now the default provider; Tavily remains
selectable. No additional dependencies were installed. Public ask/evidence schemas,
MCP `live_search` arguments and FastAPI endpoint paths are unchanged. Capabilities and
CLI health add the non-secret `search_provider` field. AI synthesis is still extractive.

| Command/check | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q --tb=short` | **73 passed, 1 skipped in 42.64s**, no failures; the skipped test is the opt-in live test |
| `$env:RUN_LIVE_SEARCH_TESTS='1'; .\.venv\Scripts\python.exe -m pytest -q tests/test_live_search.py` | **1 passed in 8.48s** using real Exa through real MCP |
| `.\.venv\Scripts\python.exe scripts/smoke_live.py` (network-approved retry) | **LIVE_SMOKE_TEST: PASS**, five real evidence records/citations; 6316 ms application time |
| `.\.venv\Scripts\python.exe -m backend.cli health` | Exit 0; live_search listed; search_provider exa; live_search_configured true |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements found |
| `.\.venv\Scripts\python.exe -m compileall -q backend tests scripts` | Exit 0 |

The initial live smoke was blocked by sandbox networking and returned a graceful
network_error, without evidence. Its approved network-enabled retry passed. The real
smoke retrieved evidence at `2026-10-17T06:54:10.571764Z`; publication dates were unknown
and explicitly labeled as such. No indexed content is claimed to have been freshly
crawled. Credentials were loaded privately from configuration and were not printed.
The opt-in live run had one pytest cache warning because separate pytest processes were
running concurrently; the actual integration test passed.

New mocked tests cover Exa authentication/request fields, extracted text/highlights,
empty or missing content, invalid responses, bounds/deduplication, timestamps,
401/403/402/429/5xx, network/deadline failures, recovery, no automatic fallback,
provider selection, and API/MCP integration. Real STDIO integration and CLI JSON/failure
checks now run for both providers. The first expanded run exposed a test-only Windows
problem: a 2 MB parameter generated an oversized pytest test ID. Explicit short IDs
fixed it; the complete regression suite above subsequently passed.

Remaining limits: no LLM synthesis, forced page recrawl, automated conflict resolution
or challenge-specific features. Run the commands in README to use the configured Exa
provider; set SEARCH_PROVIDER=tavily to select the preserved adapter.

## Historical baseline verification (before Exa)

Verified on 2026-10-17 (Asia/Karachi), in the requested workspace.

## Installed environment

Python 3.14.7; pip 26.2.1; Node 24.21.0. FastMCP 3.4.9, MCP SDK 1.30.0,
FastAPI 0.143.3, HTTPX 0.28.1, Pydantic 2.14.1, pytest 9.1.1.
75 dependency versions recorded in `requirements-lock.txt`; Windows-only packages have
platform markers. Other Python/platform combinations have not been executed here.

The initial dependency install was blocked by sandbox network restrictions. The approved
retry of `.\.venv\Scripts\python.exe -m pip install -e '.[dev]'` succeeded.
No repository or user files existed in the workspace; no original files were overwritten.
The supplied Downloads README is preserved unchanged as `docs/EXECUTION_BLUEPRINT.md`.

## Tests and checks

| Command/check | Actual result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` (final run) | **45 passed in 35.69s**, 0 failed, 0 skipped |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements found |
| `.\.venv\Scripts\python.exe -m compileall -q backend tests scripts` | Exit 0 |
| `.\.venv\Scripts\python.exe -m backend.cli health` | Exit 0, `mcp_tools=["live_search"]`, live configured false |
| CLI process tests: JSON live request with missing key | Exit 1, typed provider_unavailable, no evidence, valid JSON stdout |
| CLI process tests: retrieval disabled | Exit 1, no_evidence, no fabricated sources |
| CLI process tests: whitespace-only query | Exit 2, actionable stderr, no stdout |
| Smoke script (independently confirmed by subprocess test) | Exit 2, `LIVE_SMOKE_TEST: NOT RUN (missing key)` |
| Official Inspector `--method tools/list` | Exit 0, exactly `live_search`; output in `docs/inspector-tools.json` |
| Official Inspector `--method tools/call` | Exit 0 at protocol level; structured `provider_unavailable`, error_code `missing_key`; output in `docs/inspector-call.json` |

The full tests require no internet. They cover missing/invalid credentials, HTTP
401/403/429/5xx, one retry and recovery, timeout/network errors, malformed JSON, empty
searches, malformed evidence, deduplication, content bounds, timestamp semantics,
input validation, citation IDs, untrusted instructions, opposing excerpts and safe
unexpected failures. An isolated real MCP subprocess uses the actual production server
factory with mocked Tavily HTTP transport. A separate integration check runs CLI and API
through that subprocess and compares their outputs. Fixture data is explicitly labeled.

Initial results were 39 passed / 2 failed. The real subprocess exposed a FastMCP config
change (`FASTMCP_CHECK_FOR_UPDATES=off` required). After that fix, 40 passed / 1 failed;
the remaining test used Python stream capture without a file descriptor, incompatible
with subprocess stderr. Switching that test to file-descriptor capture fixed it.
The subsequent 41-test suite passed; four additional CLI process/exit-code checks passed
in the final 45-test run. No failing test was skipped or weakened.

## Actual Uvicorn HTTP check

Started `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765`.
It reported successful startup. HTTPX made actual loopback HTTP requests:

- `GET /health`: HTTP 200, local status ok and live_search_configured false.
- `GET /api/v1/capabilities`: HTTP 200, extractive mode, LLM/cache disabled.
- `POST /api/v1/ask` with live true: HTTP 200, provider_unavailable, actionable missing-key
  notice, empty citations/evidence, null retrieval timestamp. Real MCP was invoked.
- `POST /api/v1/ask` with empty question: HTTP 422.

## Gate status and limitations

**Offline foundation verified. Live acceptance gate remains open.**

`LIVE_SMOKE_TEST: NOT RUN (missing key)`

No successful live Tavily retrieval or real live citation was demonstrated. No LLM was
configured or called. No challenge-specific capability or frontend was implemented.
The extractive baseline preserves opposing excerpts with warnings but does not implement
automatic contradiction detection, official-source classification, or synthesized-claim
grounding. The full Phase B intelligent synthesis gate is therefore not claimed complete.

Next: set `TAVILY_API_KEY` privately, run `python scripts/smoke_live.py`, then supply the
official challenge/rules and complete the mini-brief before building a domain feature.
