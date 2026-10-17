# Loom walkthrough — target 4 minutes 30 seconds

No Loom upload is claimed. `artifacts/browser-journey.webm` is a real automated local
journey recording if the browser smoke has completed; clearly label it as recorded.

Final audit evidence and limitations: FINAL_QA_REPORT.md. Multi-Perspective Lens is
deferred; do not include invented coverage comparisons in the pitch.

## Prepare privately

1. Start the built app on http://127.0.0.1:8000 using README commands. Leave
   CREDIT_SEARCH_CONFIRMED_FREE=false. No paid APIs are needed.
2. Run `python scripts/browser_smoke.py` to confirm RSS, PDF and archive. Do not show
   `.env`, terminal history with keys, or credentials in a recording.
   For the controlled two-profile demonstration, run `python scripts/personalization_proof.py`
   once for real RSS, then `python scripts/final_qa_browser.py`. Review the actual
   profile-A/B screenshots and report. `--replay` is archived input, not live retrieval.
3. Use a fresh browser profile/incognito window for onboarding. Keep a second window
   with a real saved edition as an offline fallback. A fallback must be labeled archived.
4. Open Loom using your own account, choose browser/window + microphone capture, and
   start recording only after personal information is hidden. Loom login/upload requires
   the user; this agent has not accessed or published to Loom.

## Record

- **0:00–0:25 — Problem.** “News is scattered. The Daily Mind turns your interests and
  honest reading signals into one personal, source-linked morning paper.”
- **0:25–1:00 — Onboard.** Choose AI/software/startups; show the contrasting saved
  climate/health/world profile screenshots. Both used one real candidate batch; their
  eight selected stories differ completely in the recorded proof. Don't generalize
  that result into a benchmark or claim every input always produces disjoint editions.
- **1:00–1:45 — Generate.** Fetch real public RSS. Show source, publication/retrieval
  distinction, attributed excerpt, original link and “Why this story?” breakdown.
- **1:45–2:35 — Adaptive Interest DNA.** Like/save one story; skip another. Open DNA,
  show actual weight changes, then generate a new version. Compare a changed priority
  breakdown. Explain this is bounded heuristic learning, not an invented ML benchmark.
  A like may change a score without changing order; the recorded controlled proof
  demonstrates exactly that, then a skip changes selection/order. Say what actually moved.
- **2:35–3:15 — PDF.** Download and open the actual newspaper PDF. Match its lead/title
  and edition ID with the browser. Follow a source hyperlink if accessible.
  Show “Three things I learned”: exact source excerpts with links; headline-only
  fallback is disclosed. These are not independently verified or LLM-written claims.
- **3:15–3:45 — Archive.** Open the earlier version; show it wasn't overwritten. Reload
  to demonstrate persisted profile/archive. Show mobile layout briefly.
- **3:45–4:30 — Architecture and honesty.** Show ARCHITECTURE.md and actual test report.
  Explain MCP's actual CLI/connector purpose, RSS-first zero-spend operation, SQLite
  snapshots and local Chromium. Disclose no LLM, feed availability, localhost scope and
  pending eligibility approval. Do not invent scores or claim all source facts verified.

Stop before five minutes. Review video for secrets and clarity; copy the real Loom URL
into SUBMISSION_CHECKLIST.md yourself after upload. Do not submit automatically.
