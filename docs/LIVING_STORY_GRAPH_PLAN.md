# Living Story Graph: scoped implementation plan

Status: planned, not implemented. Daily generation and the supplied five-requirement
audit are documented in DAILY_GENERATION_QA.md. Preserve those paths and their tests.

## One feature

Let a reader open a story and see an attributed timeline of related coverage already
present in their saved editions: when it first appeared, later appearances, and exact
source excerpts. Highlight what source text changed without inventing developments.
Present a small accessible timeline first; a node-and-edge view is optional presentation,
not a reason to add a graph database, LLM or additional retrieval calls.

## First implementation slice

1. Add `backend/news/story_graph.py` as a pure deterministic projection over a bounded
   set of the reader's immutable edition snapshots (initially latest 30 editions,
   at most 150 unique article URLs). Preserve exact edition/article/source timestamps.
   Expose that bound in response metadata and label limited history.
2. Link identical canonical URLs as repeated coverage of the same source article.
   Keep distinct snapshot versions when title/excerpt changed; identical repeated
   text is another appearance, not a new reported development. Use canonicalization
   already in the news pipeline. Do not decode opaque Google redirect URLs.
3. For different URLs, suggest related coverage using bounded normalized title terms,
   explicit shared topics and known publication-time proximity. Require enough shared
   distinctive terms; a category alone cannot connect stories. Label these edges
   `possibly_related` with the matching terms and heuristic method, never factual
   event identity, corroboration, agreement, independence or contradiction.
4. Keep reader scoping in the existing route/service/store pattern. A read-only
   `GET /api/editions/{edition_id}/story-graph?article_id=...` validates article ownership
   and returns nodes, edges and provenance. Missing/sparse data returns an honest empty
   graph with a reason; another reader's IDs return the existing 404 behavior.
5. Add `frontend/src/components/story-timeline.jsx`, opened from a story card through
   an explicit action. Include loading, error, empty and success feedback. Show source
   links, publication date if known, original retrieval time and edition appearance.
   Offline/archived labels persist. Provide keyboard-accessible list/timeline layout
   on mobile; no large visualization dependency is required for the first slice.
6. Initially derive the graph on demand from snapshots with no migration. If profiling
   later demonstrates a need, add a rebuildable cache keyed by reader, snapshot IDs
   and algorithm version. Never overwrite the original editions or PDF content.

## Evidence and acceptance checks

- Exact same canonical URL across editions links deterministically without extra HTTP.
- A changed excerpt is presented as a publisher-text change, with both originals and
  timestamps; wording alone is not asserted to be a verified new fact.
- Unrelated stories in the same topic stay separate; synthetic fixtures are confined
  to tests. Cross-source candidate links clearly disclose uncertainty and match reasons.
- Missing publication dates, duplicates, malicious excerpt text, Google intermediated
  URLs and sparse evidence are handled without invention.
- Another reader cannot inspect memberships or histories from someone else's editions.
- Test determinism, bounds and stable ordering; run all daily-generation and current
  regressions. Browser test opens an actual archived timeline and follows a source link.
- Record actual retrieved evidence; if the real saved papers contain no repeated/related
  coverage, show that empty state rather than manufacture a convincing graph.
- Graph reading triggers no search, model calls or snapshot mutation. Existing web/PDF
  equality and automatic generation remain unchanged.

## Scope and demo

Target one small vertical slice: one reader, one selected story, a short attributed
timeline and clear relation reasons. Defer embeddings, semantic event resolution,
automatic contradiction detection, cross-reader graphs, recommendations, live graph
updates and multi-agent frameworks. The existing Interest DNA remains the proven
differentiator if the captured coverage is insufficient for a meaningful graph demo.

Suggested local sequence: pure projection and tests; scoped endpoint; timeline UI;
actual archived-data proof; regression/build/browser checks and results report. No
dependency purchase, deployment, Git commit or push is part of this plan.
