# Daily generation and five-requirement verification

Executed 2026-10-17, Asia/Karachi. No paid API calls, dependencies, hosting, commits
or pushes were needed. The official problem-statement PDF was not found; the five
items below follow the supplied faithful summary in the local execution contract.
This does not certify organizer eligibility or invent additional official requirements.

## Requirements audit

| Supplied official requirement | Current implementation and actual verification | Limits |
|---|---|---|
| Onboarding: capture interests with excellent UX | PASS: actual browser completed category/depth onboarding, stored preferences, reopened/cancelled editing; backend validation tests pass | English only; anonymous local identity, no production authentication |
| Fresh daily personalized newspaper PDF | Daily mechanism implemented: real automatic RSS edition opened on web and exported as matching two-page PDF; titles, takeaways, edition ID/date and hyperlinks checked; date/DST/restart/concurrency tests pass | Upstream publication freshness is not guaranteed. During outages the paper is explicitly labeled previously retrieved content, never fresh news; app must run for automation |
| Complete website, same edition, original links, archive, skips | PASS: actual full desktop/mobile browser journey, immutable version archive, skips, reload, PDF and source-link rendering. Automatic and offline snapshots both reopened from archive | Google News URLs remain labeled intermediated; external publishers/paywalls are not universally verified by this run |
| Adapt to reading/preferences over time | PASS: actual automated like/save/skip actions changed priority and next-version order; capped, idempotent, reader-scoped feedback tests pass | Deterministic explainable heuristics; opened links do not prove reading; QA clicks are not organic engagement |
| Room to explore: creative enhancements | Already implemented: Adaptive Interest DNA and extractive editorial memory. Living Story Graph has a scoped implementation plan | This is permission for creativity, not an additional mandatory named feature. Graph and Multi-Perspective Lens are not implemented |

## Implemented behavior

- FastAPI lifespan starts a cancellable local scheduler. It checks immediately at
  startup and then every configured interval (default 60 seconds), for onboarded readers.
- Each reader's timezone determines the calendar date. On-demand/webpage catch-up uses
  the same service. Missed historical dates are not filled using newly retrieved news.
- Existing date/version snapshots return before retrieval. Default generation creates
  version 1 once; existing explicit regeneration still appends versions without mutation.
- Per-reader asyncio locks and durable SQLite reader/date leases coordinate calls,
  including separate service instances. A second caller waits boundedly for the same
  edition. Generation is deadline-bounded; abandoned claims expire after 120 seconds;
  clean cancellation releases the owned claim. Failures have a default 300-second
  retry cooldown persisted across restarts. The schema addition is non-destructive.
- Bounded feed caches reuse each feed across different keyword queries within TTL.
  Query RSS is cached too. Failed feeds are cached for at most 30 seconds to avoid
  repeatedly retrying the same outage for each reader. Retrieval times are retained.
- Automatic generation uses RSS only, regardless of configured provider credits.
- During complete RSS failure/timeout, default generation can use persisted RSS with
  retrieval age at most seven days (configurable). Non-RSS, future-dated retrievals
  and expired content are excluded. Web/PDF prominently label `offline_fallback`.
- Offline fallback creates a new assembly snapshot for today's date; it does not
  relabel yesterday's edition or change source timestamps. The original archive stays
  immutable. A stable offline paper can be explicitly regenerated after reconnection.
- Without usable saved RSS, generation returns the existing graceful 503 response;
  archives remain readable. Explicit regeneration retains its prior live-success rule.

## Actual commands and results

| Command/check | Executed result |
|---|---|
| Before changes: `python -m pytest -q --tb=short` | 106 passed, 1 skipped in 59.89s |
| Initial targeted daily/newspaper tests | 29 passed in 7.78s |
| Initial expanded full suite | 119 passed, 1 skipped in 67.06s |
| Final full suite after cancellation/timeout coverage | **121 passed, 1 skipped in 66.03s**, no failures |
| `npm.cmd run build` in frontend | **PASS**, Vite 7.3.7, 1,582 modules, 2.38s |
| `python -m pip check` | No broken requirements found |
| `python -m compileall -q backend tests scripts` | Exit 0 |
| `python scripts/daily_generation_smoke.py` | PASS: actual startup RSS generation, web/PDF/archive, stable on-demand reuse; explicit simulated outage using actual persisted RSS |
| `python scripts/daily_generation_smoke.py --full-journey` | PASS again, plus existing complete browser journey including onboarding, feedback, versioned archive, reset/preferences, reload and 390px mobile |
| Working source scan | No configured-key or private-key matches; `.env` absent from tracked/publication candidates |
| `git diff --check` | PASS |

The optional live Exa pytest was skipped. No Exa, Tavily or model request is needed
for these runs. The smoke server explicitly uses empty provider keys and disables
credit-based search. User data/server on port 8000 were left alone: QA used isolated
SQLite files and OS-assigned localhost ports, then shut down its owned servers.

## Live proof and artifacts

Latest automatic edition: `03b914db-8f07-4577-aa25-93c1622e077b`.
Four real RSS stories, including attributed Dawn/BBC and Google News-linked coverage.
Both automatic and explicitly simulated-outage papers exported as two-page PDFs.
All saved article titles and takeaways appeared in their PDFs; edition ID/date and
hyperlinks matched. Opening either automatic edition made **zero browser generation
calls**. A same-day explicit default API request returned the identical saved snapshot.
The previous snapshot remained unchanged across server restart and fallback creation.
Both browser checks reported zero page errors. All four PDF page images were inspected;
text/disclosures were readable with no clipped article content. A mostly empty final
page from keeping editorial memory together remains an accepted layout limitation.

The existing full journey used eight-story papers and a three-page PDF. Real automated
feedback changed measured order, including positions 3 to 2 and 6 to 4. This verifies
application behavior, not model accuracy or organic reader engagement.

Ignored local artifacts:

- `artifacts/daily-generation-smoke.json`: actual combined execution results/source URLs.
- `artifacts/automatic-daily.pdf` and `offline-daily.pdf`: matching saved papers.
- `artifacts/automatic-daily-web.png` and `offline-daily-web.png`: actual browser views.
- `artifacts/automatic-daily-page-1/2.png`, `offline-daily-page-1/2.png`: rendered PDF pages.
- `artifacts/browser-smoke.json`, `daily-mind-live.pdf`, existing journey screenshots
  and local WebM: latest existing full browser check, not a Loom upload.
- `artifacts/daily-generation-security.json`: source scan results.
- `checkpoints/before-daily-generation.zip`: source-only recovery checkpoint, no secrets.

## Remaining limitations

One worker is recommended. SQLite leases prevent concurrent retrieval for the same
reader/date across workers; feed response caches are per process, so different readers
in different processes may fetch the same feed. A process crash after an upstream
request but before saving can cause a later retry: exactly-once external retrieval is
not claimed. On restart an abandoned claim can delay catch-up until lease expiry.
Large reader populations are out of scope; the local scheduler processes readers
sequentially, so intervals measure the pause after a sweep, not a hard delivery SLA.

No jobs run while the machine/app is off, and no missed-date editions are fabricated.
There is no OS wakeup, cloud cron, notification delivery or scheduling by a chosen
morning hour. A saved offline edition is not silently upgraded to fresh content.
Unknown publication dates and older coverage remain disclosed. No billing, model
synthesis, new graph functionality, public deployment or final submission occurred.
Event-start/monitored-commit eligibility and Loom upload remain unresolved.

## Source/document files changed

- `backend/config.py`: bounded daily/fallback settings.
- `backend/main.py`: lifespan task ownership and graceful cancellation.
- `backend/news/scheduler.py`: startup catch-up, periodic checks and error isolation.
- `backend/news/service.py`: shared idempotent job, durable claim, deadlines and fallback.
- `backend/news/store.py`: additive leases, onboarded readers and validated stored RSS.
- `backend/news/discovery.py`: bounded per-feed success/failure caching across queries.
- `backend/news/pdf.py`: prominent offline disclosure from saved snapshot.
- `frontend/src/main.jsx`: current-date catch-up and visible offline provenance.
- `tests/test_daily_generation.py`: 15 new date/DST/concurrency/restart/cache/lifecycle/
  fallback/cancellation/timeout tests. Existing tests preserved.
- `scripts/daily_generation_smoke.py`: isolated real automatic/browser/PDF/outage proof.
- `.env.example`, `README.md`, `ARCHITECTURE.md`, `docs/API.md`, this report,
  `docs/LIVING_STORY_GRAPH_PLAN.md`, `FINAL_QA_REPORT.md`, `IMPLEMENTATION_STATUS.md`.

Changes remain local and uncommitted. No automatic push was performed.
