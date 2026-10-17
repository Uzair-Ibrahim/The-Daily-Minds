# The Daily Mind — final product audit and QA

Latest main integration: 183 passed, 1 optional skipped; production build and combined
real-browser regression passed. The first-three-image limit is removed and genuine
photos at story positions 4 through 8 were verified. See MAIN_INTEGRATION_REPORT.md.

Living Story Graph follow-up (2026-10-17): **167 passed, 1 skipped in 113.18s**;
production frontend build and genuine RSS / archived replay browser / PDF proof pass.
Local CPU semantic embeddings, reader-scoped story persistence, follow ranking and
continuing-story snapshots are now implemented. See
[actual implementation and limits](LIVING_STORY_IMPLEMENTATION_REPORT.md). Earlier
missing/planned feature statements below describe their historical audit dates.

Latest image follow-up: **154 passed, 1 optional skipped in 77.53s**; Vite production
build passed in 2.48s. Actual publisher images, desktop/mobile rendering, matching
image-bearing PDF, missing/failed image fallback and the existing full browser journey
passed. See [IMAGE_SUPPORT_REPORT.md](IMAGE_SUPPORT_REPORT.md) for feed-level evidence,
changed files and limits. All changes remain local; no commit or push was made.

Latest daily-generation audit: **121 passed, 1 optional skipped**; production build and
real automatic-RSS/browser/PDF plus offline-fallback and full user-journey checks pass.
See [daily generation and five-requirement verification](docs/DAILY_GENERATION_QA.md).
The original audit below is retained as historical evidence. Daily local scheduling is
now implemented; no changes from this follow-up were committed or pushed.

Publication update (2026-10-17): the owner subsequently supplied the GitHub repository
and authorized an initial snapshot. Publication blockers below describe the earlier
local audit. Event-start/monitored-development compliance remains unresolved. See
docs/PUBLICATION.md.

Verified 2026-10-17 (Asia/Karachi). This report records executed results, not a prediction
of judging scores. No new dependencies, paid API calls, billing, deployment, repository
creation, Git history changes or Loom upload occurred during this audit.

## Requirements matrix

| Requirement | Implementation state | Actually tested / limits |
|---|---|---|
| Personalized onboarding | Fully implemented locally | Fresh real browser onboarding → preferences saved → actual RSS edition; edit/cancel/reset tested |
| Daily personalized newspaper PDF | Fully implemented on demand | Reader timezone/date/version tests; actual 3-page sample PDF parsed, all article and takeaway text matched, hyperlinks present, all pages rasterized/visually inspected |
| Complete webpage reader | Fully implemented for attributed excerpts | Desktop 1440px + mobile 390px, reading/actions/empty/error/loading states; no page errors or horizontal overflow |
| Original article links | Partially verified across sources | Actual Guardian anchor navigation returned HTTP 200 on the original publisher host. Google News links are explicitly labeled intermediated; not every external URL/paywall is verified |
| Previous editions | Fully implemented locally | Actual owned server stopped/restarted with the same SQLite file; saved JSON identical and archive available; unit tests also cover offline retrieval |
| Learning from behavior | Fully implemented as deterministic heuristics | Real automated like/save/skip/opened actions, capped weights, repeated actions do not double count; requested profiles and feedback changes proven |
| Explainable “Why this article?” | Fully implemented | Actual interest/keyword/recency/diversity/repetition components visible; no confidence or trained-ML claims |
| Three Things I Learned | Implemented extractively | Exact source sentences/excerpts, links and source attribution saved in snapshot; headline-only fallback labeled; sparse/malicious data tests pass |
| Multi-Perspective News Lens | Missing / deliberately deferred | RSS excerpts + title overlap cannot reliably prove same event, independence, agreement or material disagreement. No fake comparison shipped |
| Automated overnight scheduling | Missing / outside current MVP | Editions are generated on demand per local date; no background scheduler claimed |
| Public repository + monitored event-start history | Blocked | Workspace has no Git history; pre-existing-work eligibility unknown. User approval/rule decision required before publication |
| Loom ≤5 minutes | Not uploaded | Actual local automated WebM exists; final ≤5-minute Loom script exists; user login/recording/upload still required |
| Architecture diagram | Implemented | Updated ARCHITECTURE.md contains Mermaid and actual execution/data flow |

## Audit findings and fixes

1. **False keyword matches:** custom `AI` matched `said`. Word/phrase boundaries now
   prevent this, with regression tests for both a nonmatch and legitimate AI-powered text.
2. **DNA/ranking mismatch:** scoring used uncapped raw feedback even when the displayed
   weight hit 0.1/3 limits. Ranking now uses the effective capped weight difference.
   Tests prove displayed weight × 3 equals the actual interest+feedback contribution.
3. **Timestamp labeling:** the browser footer labeled generation time as retrieval.
   It now says “Edition generated” and points to original per-story retrieval times.
4. **Headline-only closing section:** replaced new editions' headline repetition with
   extractive editorial memory. Prefer usable source text and distinct publishers;
   explicitly label headline-only evidence. Old editions keep their original snapshots
   and render with their legacy headline section; no destructive migration.
5. **Source-link transparency:** Google News URLs are now labeled “Open via Google News”
   in reader/PDF instead of implying a direct publisher URL. No opaque-link decoding,
   paywall bypass or invented canonical URLs.
6. **Candidate truncation bias:** bounded RSS candidates now interleave feeds before
   the 150-result cap, rather than systematically dropping later science/sport feeds.

The polished masthead, editorial layout and responsive grid were retained. No broad
frontend redesign, model integration or provider rewrite was needed.

## Executed commands and results

| Command | Actual result |
|---|---|
| Pre-change `python -m pytest -q --tb=short` | 99 passed, 1 skipped in 59.77s |
| Targeted editorial/profile/newspaper tests | 22 passed in 7.34s before the additional Google-headline regression |
| Final `python -m pytest -q --tb=short` | **106 passed, 1 skipped in 96.23s**, zero failures |
| `npm.cmd run build` in frontend | **PASS**, Vite 7.3.7, build 5.18s |
| `python scripts/personalization_proof.py` | **PASS**, fresh capture of 150 real RSS articles; common candidate batch for both profiles |
| `python scripts/personalization_proof.py --replay` | **PASS**, explicitly archived real-RSS replay, not claimed as new live retrieval |
| `python scripts/final_qa_browser.py` | **PASS**, both profiles, direct publisher navigation, PDF, actual server restart, missing credentials, simulated 503, plus complete fresh real-RSS journey |
| `python scripts/browser_smoke.py` (called by final QA) | **PASS**, new onboarding → actual live RSS → feedback → changed ordering → PDF → archive → reset/preferences → mobile + recording |
| `python -m pip check` | No broken requirements found |
| `python -m compileall -q backend tests scripts` | Exit 0 |
| Final secret/config scan | 78 source/build/doc files checked; 0 configured-key matches; .env ignored; credit search flag false |

The single skipped pytest test is explicitly opt-in Exa integration. RSS requires no
credentials. Credit-based providers stayed disabled; missing-key behavior was tested.

The browser harness initially failed its Windows restart/port checks. Its helper routes
were registered after the static-site mount and thus shadowed; this was corrected in
the **QA harness only**. The harness now verifies ownership using a run ID and uses an
OS-assigned port on each process start, avoiding Windows TIME_WAIT. The successful
restart check compares the same SQLite snapshot across two actual processes; it does
not claim the port stayed constant. The existing user app on port 8000 was left alone.

## Controlled personalization proof

Profiles requested by the user:

- **A:** technology 2.5 / business 1.5; AI, software engineering, startups.
- **B:** science 2.5 / world 1.8; climate, health, world news.

Both used the **same 150 real retrieved articles and ranking time**, not separate fixture
sets. Each eight-story paper had eight selections not present in the other, with distinct
leads. This proves preference-dependent selection, not accuracy or superiority.

One actual automated `liked` event raised the selected priority score **11.478 → 12.528**
but did **not** change order in that run; this is reported honestly. A separate actual
automated `skipped` event removed the previously second-ranked story from the next eight
selections, and the third-ranked story moved to second. These are application QA clicks,
not organic engagement, proof of completed reading or ML benchmark metrics.

Evidence: artifacts/personalization-candidates.json, personalization-proof.json,
profile-A-edition.json and profile-B-edition.json. Replays retain original retrieval
timestamps and are labeled archived. Controlled readers use a separate QA SQLite file.

## Browser, publisher and PDF evidence

- Requested Guardian article opened through the actual UI anchor and loaded HTTP 200
  at the same original publisher host. Exact public URL is in final-browser-qa.json.
- Saved edition JSON was identical before/after actual server shutdown/restart.
  SHA-256: `ebe94b49e5b9c10639ad9b96c4298ef1374540ce7152d19d7edfd46dff690fc6`.
- Final sample PDF: **3 pages**; all saved article titles and extracted takeaway text
  found in parsed PDF; source hyperlink annotations present. Page images inspected;
  variable whitespace from keeping long headlines/articles intact is accepted. No
  requirement for a fixed two-page length is invented.
- Explicitly simulated HTTP 503 showed a labeled error + empty state, without invented
  articles. This is separate from successful real RSS retrieval.
- Full fresh real-RSS journey: eight-story paper, changed story order, actual PDF,
  persisted archive, reset/edit controls, 390px mobile, zero browser page errors.

Artifacts (ignored/local):

- final-browser-qa.json — machine-readable full audit results.
- final-sample-paper.pdf and final-pdf-page-1/2/3.png — actual sample and rasterized pages.
- profile-A-browser.png / profile-B-browser.png — actual contrasting editions.
- profile-A-memory.png / profile-B-memory.png — exact editorial memory screenshots.
- profile-A-mobile.png / profile-B-mobile.png — mobile screenshots.
- simulated-network-error.png — explicitly simulated failure UI.
- browser-smoke.json, browser-journey.webm and existing journey screenshots — actual
  automated local run; not a Loom upload.
- final-security-check.json — actual source/build scan and no-payment guard state.

## Exact source/document files changed in this audit

Modified:

- backend/news/discovery.py — fair bounded feed interleaving.
- backend/news/ranking.py — bounded phrase matches and actual capped DNA contribution.
- backend/news/service.py — saved extractive takeaways/method metadata.
- backend/news/pdf.py — memory content + intermediary link labels.
- frontend/src/main.jsx — memory component + provenance/time labels.
- scripts/browser_smoke.py — optional QA base URL, preserves default localhost:8000.
- README.md; docs/DAILY_MIND_README.md; docs/API.md; docs/DECISIONS.md; docs/RESULTS.md.
- IMPLEMENTATION_STATUS.md; ARCHITECTURE.md; DEMO_SCRIPT.md; SUBMISSION_CHECKLIST.md.

Created:

- backend/news/memory.py
- frontend/src/components/editorial-memory.jsx
- scripts/personalization_proof.py
- scripts/final_qa_browser.py
- scripts/qa_server.py (test harness only; not production API)
- tests/test_editorial.py
- tests/test_personalization_proof.py
- FINAL_QA_REPORT.md
- checkpoints/before-final-qa.zip and ignored review artifacts.

No `.env`, dependency manifest/lockfile, Git history or working provider module was changed.

## Ready for judging and remaining blockers

Ready locally: onboarding, current RSS retrieval, genuine profile separation, explainable
behavior learning, editorial reader, attributed memory, archived versions, original
links with intermediary disclosure, downloadable paper and responsive UI.

Remaining: public publication/eligibility decision, actual Loom upload, universal source
availability, scheduled generation, production authentication, true fact/contradiction
verification and the optional Multi-Perspective Lens. No cloud deployment is claimed.

Local app URL: **http://127.0.0.1:8000**. An existing app was already listening there;
restart your own server to load changed Python modules before judging. The isolated QA
servers shut down automatically. See DEMO_SCRIPT.md for the exact final review sequence.
