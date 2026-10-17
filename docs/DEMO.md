# Baseline demo — 90 seconds

Historical baseline only. The current product walkthrough is in ../DEMO_SCRIPT.md;
use the RSS-first zero-spend workflow from the root README.

This demonstrates infrastructure, not a final challenge differentiator.

1. 0–15s: `python -m backend.cli health` shows the real MCP tool list and configuration booleans.
2. 15–45s: Run the first question from `backend/demo_queries.json` with `--live`.
   Point to the extractive label, source URLs and retrieval/publication distinction.
3. 45–65s: Run the second independent query as backup. If no key/network exists, show
   the explicit failure. Never represent a test fixture as successful live search.
4. 65–80s: Show `/docs` and the shared `/api/v1/ask` contract, then actual test results.
5. 80–90s: State limitations: snippet extraction, unknown authority, no automated conflict
   resolution; problem-specific capability waits for official challenge text.

Architecture explanation: CLI and FastAPI share an orchestrator. It launches a local
FastMCP subprocess and calls `live_search` over MCP STDIO. Only the tool server calls
Tavily. Normalization bounds snippets, deduplicates URLs and preserves provenance.
The orchestrator returns attributed excerpts with validated citations and limitations.
Provider errors and timeouts yield typed failures rather than invented answers.

Backup checklist: verify keys privately, run the live smoke script, retain terminal test
output, check both independent queries, and record a permitted working demonstration.
Clearly label any recording as recorded. Hide `.env`, auth headers and console history
containing secrets. Do not describe offline tests as proof of internet connectivity.
