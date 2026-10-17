# Main integration and images on every story

Verified 2026-10-17. The owner authorized integrating the image/engagement feature into
main so the combined application could be reviewed there. Feature commit `599ba19` was
merged with a truthful local merge commit. No remote push or history rewrite occurred.

Existing uncommitted Living Story Graph work was preserved in a source-only checkpoint
and named Git stash `4683811cc35aa1b9db8fc390a16d5d6300fbf9c2`, then restored after the
merge. The backup stash was retained. Overlaps in routes, PDF, React and CSS were resolved
by retaining both graph and image/engagement behavior. Graph tables, story follow APIs,
timeline UI, continuing-story sections, ranking updates, tests and optional local model
configuration remain present. No environment keys or user databases were copied/reset.

## Three-image limit fixed

The article card previously rendered `ArticleImage` only when `index < 3`. That condition
is removed: every story can now display its own publisher image. Non-lead images remain
lazy-loaded to avoid fetching every asset immediately. Missing/restricted images use the
compact text treatment; an unrelated photo is never substituted. PDF still embeds one
lead image to preserve the established print layout.

The controlled real-source browser proof now selects eight actual retrieved stories,
including a deliberately legacy-shaped Dawn snapshot and one Google News entry without
image metadata. It found eight image components and actually rendered publisher photos
on **positions 4, 5, 6, 7 and 8**. The no-photo story showed its compact fallback. Photo
metadata and bytes remained cached across loader restart; saved editions stayed immutable.

## Actual integrated verification

- Combined main suite: **183 passed, 1 optional Exa test skipped in 104.87s**.
- Combined frontend production build: **PASS**, Vite 7.3.7, 1,586 modules, 2.87s.
- `python scripts/image_engagement_smoke.py --full-journey`: PASS on integrated main,
  including genuine fourth-story photo, Dawn image, reversible feedback/counts, sharing,
  reading list, PDF, archive/reset/preferences and mobile. Eight-story existing journey
  exported a four-page PDF with the graph continuation sections.
- Updated `python scripts/image_engagement_smoke.py`: PASS with photos explicitly checked
  at positions 4–8; eight-story matching PDF had three pages and one embedded lead photo.
  Zero browser page errors and no 390px horizontal overflow.
- Real bounded retrieval: 150 candidates in 4.386s in the latest controlled proof.
  Primary journey recorded 28 local image/metadata requests, two outbound metadata/feed
  requests and three outbound image requests; subsequent loader restart used no network.
- Updated server returned HTTP 200 for `/`, `/health`, `/api/reading-list` and
  `/api/stories/updates` on `http://127.0.0.1:8001`.

Artifacts are local/ignored: `artifacts/image-engagement-smoke.json`, browser screenshots,
`engagement-dawn-paper.pdf`, `browser-smoke.json` and the checkpoint ZIP. Test clicks and
simulated failures are QA evidence, not organic engagement. No paid API or model service
was used; the graph's installed local model remains offline at runtime.

## Running main for review

The previous service on port 8000 exposed the old backend and lacked the merged routes.
Its owning process could not be safely identified, so it was left untouched. The updated
main app is running on **http://127.0.0.1:8001**, with backend auto-reload limited to the
`backend` directory. The production frontend has already been rebuilt. Runtime process
information and logs are in ignored `artifacts/main-app-process.json` and referenced logs.
Future backend edits reload automatically; frontend source edits need another Vite build.

Images still depend on publisher availability. Google News may provide none; public
page restrictions and unknown CDN hosts remain respected. No universal image licensing
permission is asserted. Existing event-start/monitored-commit and Loom limitations remain.
