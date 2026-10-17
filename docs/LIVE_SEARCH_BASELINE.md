# NaSCon live-evidence baseline

Historical preserved guide. Read the current root README for The Daily Mind and its
RSS-first zero-spend defaults. CREDIT_SEARCH_CONFIRMED_FREE must now be explicitly
confirmed before any credit-based MCP search; the instructions below predate that guard.

Official problem statement, rules, submission deadline and judging criteria: **not supplied**.
This is reusable infrastructure, not the final challenge innovation. The supplied execution
contract is preserved in [docs/EXECUTION_BLUEPRINT.md](docs/EXECUTION_BLUEPRINT.md).

Implemented scope: Phase A CLI + real STDIO MCP + Exa (primary) or Tavily (optional), plus the shared FastAPI
endpoints explicitly ordered in Section 15. No frontend, authentication, domain tools,
LLM synthesis, persistent database, or speculative challenge features.

## Install (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Set EXA_API_KEY in .env locally. Never commit credentials.
```

For the exact tested dependency set, install `requirements-lock.txt` first, then
`python -m pip install -e ".[dev]"`. Python 3.11+ is required.

```powershell
python -m pip install -r requirements-lock.txt
python -m pip install -e ".[dev]"
```

## Run

Configure `.env` (edit an existing file; do not overwrite your credentials):

```dotenv
SEARCH_PROVIDER=exa
EXA_API_KEY=your_real_exa_key
LLM_PROVIDER=none
```

Exa is the default. To retain Tavily, set `SEARCH_PROVIDER=tavily` and
`TAVILY_API_KEY=your_real_tavily_key`. Only the selected provider's key is required.
There is no silent fallback between providers; a missing/invalid selected key returns
a clear failure. Restart Uvicorn after changing `.env`.

The adapter uses the [official Exa Python SDK](https://github.com/exa-labs/exa-py),
`AsyncExa.search(..., contents={"highlights": True})`, with `x-api-key` authentication.
The tested SDK version is pinned to `exa-py==2.25.0` in project dependencies and the
lockfile; `python -m pip install -e ".[dev]"` installs it. Exa's SDK brings an OpenAI
package dependency; this app does not invoke an LLM or change the reasoning architecture.
Highlights provide relevant source excerpts without requesting full pages or synthesis.
It preserves `publishedDate` when timezone-aware, uses actual UTC request/retrieval
timestamps, bounds and deduplicates extracted sources, and never uses titles as evidence
when extracted content is missing. Exa relevance scores remain null; no confidence score
is invented. `live=true` performs a fresh API request but does not force a new crawl of
every source page. Indexed content may be older; publication dates may be unknown.

```powershell
python -m backend.cli health
python -m backend.cli ask "What does the official Python documentation say about asyncio timeouts?" --live
python -m backend.cli ask "What does the official Python documentation say about asyncio timeouts?" --json --live
uvicorn backend.main:app --reload --host 127.0.0.1
python -m pytest -q
python scripts/smoke_live.py
```

The CLI starts/manages its own MCP STDIO subprocess using the active Python interpreter.
No second server terminal is needed. `health` lists tools over the real protocol without
using a provider key. Health proves local MCP availability, not external service access.
Health and capabilities also report `search_provider` without exposing credentials.
Diagnostic output is on stderr; `--json` emits one JSON object on stdout.

Exit codes: 0 = evidence returned (`ok` or `partial`); 1 = no evidence/provider/MCP
failure; 2 = invalid input/configuration. `partial` means usable evidence survived
discarding malformed upstream records. The smoke script returns 2 when skipped for a
missing key, and 1 on retrieval failure. A skipped smoke test is not a pass.
Without `--live`, no retrieval occurs. It returns `no_evidence` unless an explicitly
requested in-process cache entry exists.
Production has no offline fixture switch. Test fixtures are confined to `tests/`.

## Evidence caching

Fresh search remains the default: `--live` and API requests without `use_cache=true`
always invoke MCP. Successful retrievals populate a bounded, 64-entry in-memory TTL
cache. API callers may add `"use_cache": true` to reuse an entry for the same provider,
question and source count. Hits return `freshness="cached_within_ttl"`, a cache notice,
and the original evidence/retrieval timestamps. Expired entries and failures are never
served. Set `LIVE_CACHE_TTL_SECONDS=0` to disable caching; default is 180 seconds.

The cache belongs to one running application process. It is cleared on restart and is
not shared across Uvicorn workers or separate terminal commands. The additive CLI
`--cache` option permits in-process reuse; a standalone invocation starts empty.
With `live=false,use_cache=true`, an API cache miss returns `no_evidence` without
network access. With `live=true,use_cache=true`, a cache miss performs live retrieval.

Optional real Exa integration test (uses API credits and requires network access):

```powershell
$env:RUN_LIVE_SEARCH_TESTS = "1"
python -m pytest -q tests/test_live_search.py
Remove-Item Env:RUN_LIVE_SEARCH_TESTS
```

Without this opt-in, the live test is explicitly skipped; all other tests use mocked
provider HTTP responses, including real MCP subprocess checks for both providers.
`python scripts/smoke_live.py` checks whichever provider is selected in `.env`.
HTTP 401/403, 402 (Exa credits), 429, 5xx, bad JSON and network/timeout errors produce
typed failures without upstream error bodies or secret-bearing diagnostics.

## Data integrity and limits

- Every live ask calls MCP unless cache reuse is explicitly requested and a valid entry exists.
- Exa API-key / Tavily bearer authentication stays in subprocess configuration and request headers.
  Provider error bodies and raw exceptions are never returned to users.
- Requests have an overall provider deadline, connection/read timeouts, and at most one
  jittered retry for Exa connection/read failures or HTTP 429/5xx (Tavily retries 429/5xx).
  Authorization errors are never retried. MCP startup,
  invocation and shutdown have an additional bounded deadline.
- Queries: 1–2000 characters; sources: 1–8; snippets: 3000 characters; titles: 300.
  HTTP(S) source links retain their full URL. Fragment-insensitive duplicate detection
  preserves the first original URL. Publication dates without a timezone remain unknown.
- The output is **extractive**, even if LLM environment variables are present. Each excerpt
  is attributed to a real returned evidence record; no analytical synthesis is claimed.
- Search relevance scores, when supplied by Tavily, are not confidence estimates. Official
  authority is unknown. Retrieval date does not establish publication date or truth.
- Retrieved instructions are untrusted text, displayed as excerpts. They cannot select
  tools, execute code, or trigger follow-up HTTP calls. Any future UI must escape text.
- Opposing snippets are retained with uncertainty warnings. Automatic contradiction
  detection and factual grounding of LLM-generated claims are **not implemented**.
- Provider responses are checked for size after HTTP download; this is a local MVP,
  not a hardened public service. Keep the backend bound to localhost.
- The pinned SDK has no public HTTP-client/timeout injection API. The adapter supplies
  its managed HTTPX client through the SDK's `_client` compatibility hook, verified by
  tests. SDK upgrades must retest this hook. The client always closes after each search.
- JSON output escapes Unicode for Windows console compatibility; normal CLI output uses UTF-8.

See [API contract](docs/API.md), [decisions](docs/DECISIONS.md),
[demo](docs/DEMO.md), [attributions](docs/ATTRIBUTIONS.md), and
[actual verification results](docs/RESULTS.md).

## MCP Inspector

```powershell
npx @modelcontextprotocol/inspector
```

Select STDIO. Command: absolute path to `.venv\Scripts\python.exe`.
Arguments: `-m backend.mcp_server`. Working directory: this project directory.
List tools and invoke `live_search` with `{"query":"Python asyncio", "max_results":2}`.
The server loads this project's `.env`. Never paste credentials into tool arguments.
Node 24 is available locally. See the official Inspector CLI docs before scripting CLI flags.

Verified Inspector CLI commands (Windows, from this project directory):

```powershell
npm.cmd exec --yes --package @modelcontextprotocol/inspector -- mcp-inspector --cli --config scripts/inspector.json --server baseline --method tools/list --format json
npm.cmd exec --yes --package @modelcontextprotocol/inspector -- mcp-inspector --cli --config scripts/inspector.json --server baseline --method tools/call --tool-name live_search --tool-arg 'query=Python asyncio documentation' max_results=2 --format json
```

The bundled Inspector config uses the Windows virtual environment path. Adjust its
interpreter path on other platforms. Tool-call transport success can still contain
`status=provider_unavailable`; inspect the structured result, not only the process exit.

## Next gate

Supply the official problem/rules before selecting the single killer feature. Fill the
challenge mini-brief in `docs/DECISIONS.md`, then define its acceptance test. Frontend and
optional synthesis remain deferred until that scope and the remaining time justify them.
