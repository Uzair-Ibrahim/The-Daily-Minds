# Living Story Graph implementation

Implemented 2026-10-17 (Asia/Karachi) directly in
`C:\Users\AK.COM\OneDrive\Desktop\Nascon Ai Hackathon`, branch `main`, following the
owner's correction to integrate in this project. The previously created sibling worktree
`C:\Users\AK.COM\OneDrive\Desktop\daily-mind-living-story` and its
`feature/living-story-graph` branch were not modified. Base: `8838a0d`. These new changes
are uncommitted and were not pushed.

## Delivered behavior

- Free local CPU MiniLM embeddings, lazy loading, batched normalized inference and
  persistent text/model-keyed vector cache. Runtime never downloads model weights or
  calls hosted inference. Optional model absence retains deterministic matching.
- Conservative hybrid matching: shared distinctive headline terms, capitalized name
  cues, explicit numbers, publication-date proximity and semantic similarity. Possible
  cross-source associations are labeled uncertain; no independent verification claimed.
- Persistent reader-scoped story clusters, canonical article URL membership and
  idempotent source-text versions. Repeated fetches do not duplicate observations.
- Actual publisher headlines/excerpts, source URLs, publication time and observation
  time appear in the timeline. Newly observed older coverage retains its original dates.
- Source-text differences are attributed to original evidence. Sparse evidence says
  “Not enough source evidence to determine what changed.” No contradiction detection,
  inferred causal narrative or fabricated event dates.
- Follow/unfollow and bounded +1.5 ranking bonus for new coverage, limited to half an
  edition's boosted slots. Prior edition article IDs reduce repetition. Existing topic
  likes/saves/skips and Interest DNA remain intact; opening stays a weak existing signal.
- Expandable article timelines, match explanations, follow controls, saved continuing
  stories and “Since your last edition” observations where timestamps support them.
- Future editions save a bounded continuing-story section, rendered from the same
  snapshot in browser and PDF. Legacy archived editions remain unchanged.
- Typed reader-scoped APIs: `GET /api/stories/{id}`, `PUT /api/stories/{id}/follow`,
  `GET /api/stories/updates`. Detail includes timeline and evidence links, avoiding
  separate redundant timeline/related endpoints. Invalid/missing reader and story
  identifiers are rejected.

## Local model and resources

Actual model: `sentence-transformers/all-MiniLM-L6-v2`, Apache-2.0 per the
[model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2).
Implementation follows the official
[SentenceTransformer API](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html).
CPU only, 384 dimensions. Installed optional sentence-transformers 5.7.0 with torch
2.14.1 and transformers 5.20.1 on Python 3.14.7 / Windows x64. No billing, paid APIs
or credentials were used. Weights live outside Git at
`C:\Users\AK.COM\.cache\daily-mind-models`.

Measured setup: download/import/load 55.513 seconds; first two-text inference batch
0.098 seconds. Process working set and peak working set were both 578.2 MB at that
measurement, including Python/framework/model. These are process measurements, not
model-only RAM or universal performance guarantees. A separate cold evaluation process
including model import/loading/cache work took 19.681 seconds for its embedding step.
Hardware checks: 88.1 GB free disk before installation; 16.99 GB physical RAM, 3.96 GB
available at the later resource check. Initial WMI hardware inspection was denied;
Windows memory APIs provided the later measurement. No GPU assumed.

## Actual evaluation

Fixture: `tests/fixtures/story_pairs.json`, 14 synthetic development pairs, eight
positive and six negative. Includes broad-topic negatives, different product launches,
dates/numbers, different locations, sparse text, missing dates, later-discovered older
coverage, same URL with changed headline, syndication-like headlines and opposite-looking
wording treated as related coverage without asserting contradiction. Persistence,
duplicate fetch and cross-day behavior are separately covered by storage/service tests.

| Method | TP | FP | TN | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|
| Keyword-overlap baseline | 8 | 6 | 0 | 0 | 0.5714 | 1.0000 |
| Semantic similarity alone | 8 | 4 | 2 | 0 | 0.6667 | 1.0000 |
| Hybrid | 8 | 0 | 6 | 0 | 1.0000 | 1.0000 |

These are executed results on a small development set used to exercise the rules, not
independent research-grade accuracy. There was no pre-existing event matcher; the
keyword baseline is a declared overlap comparator, not a claim about prior production
event resolution. Full confusion counts and errors: `artifacts/story-evaluation.json`.
Reproduce: `python scripts/evaluate_story_graph.py`.

## Genuine RSS and browser proof

Actual public RSS capture retrieved 143 articles. The matcher connected BBC and Dawn
coverage with shared headline terms `russia, sanctions, trump, waives` and local
semantic support. It rejected an unrelated Pakistan coverage example. Source text and
original timestamps are retained in `artifacts/living-story-rss.json`; the proof does
not independently verify publisher claims.

`scripts/living_story_demo.py` replayed these genuine articles through two editions in
a temporary SQLite database, using an OS-assigned localhost port. Actual Chromium
checks verified timeline opening, follow/unfollow, no desktop/mobile horizontal
overflow, no page errors, saved snapshot immutability and matching two-page PDF.
The PDF pages were rasterized and visually inspected; no clipped or overlapping story
content was observed. The first inspected version had an orphan section heading;
print break rules were refined before final replay.

Artifacts (ignored by Git):

- `artifacts/living-story-demo-live.json`: actual retrieval/browser result.
- `artifacts/living-story-demo-replay.json`: final saved-capture replay result.
- `artifacts/living-story-desktop.png`, `artifacts/living-story-mobile.png`.
- `artifacts/living-story-paper.pdf`, `artifacts/living-story-pdf-1.png`,
  `artifacts/living-story-pdf-2.png`.

The demonstration deliberately replays saved real articles in two editions, labeled
archived/replayed. It does not fabricate a later news development, observation time,
multi-day live run or recency claim. Real multi-day operation requires future RSS
retrievals. “Since your last edition” correctly stays empty if no newly observed
evidence is newer than that edition. Its positive cross-day behavior and ranking boost
are tested with explicitly synthetic test-only fixtures.

## Regression and setup

Before changes: **154 passed, 1 skipped in 78.22 seconds**.
First complete regression after core integration: **164 passed, 1 skipped in 130.84
seconds**. Expanded feature suite: **13 passed**. Final full regression:
**167 passed, 1 skipped in 113.18 seconds**. Final saved-capture browser replay also
passed, including the new-coverage ranking bonus, follow/unfollow, immutable snapshots,
desktop/mobile layout and two-page PDF. Vite production build passed (1584 modules, 4.97 seconds);
`pip check` passed. Windows sandbox restrictions required running the build, model
download and Chromium/network demonstration outside the sandbox. No source changes
were blocked. The real `.env` was not edited or copied.

Run locally after restarting the backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[stories]"
.\.venv\Scripts\python.exe scripts/setup_story_model.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/evaluate_story_graph.py
.\.venv\Scripts\python.exe scripts/living_story_demo.py
.\.venv\Scripts\python.exe scripts/living_story_demo.py --replay artifacts/living-story-rss.json
```

Choose **Make a new edition** in the existing UI. Old editions intentionally do not gain
new badges. `STORY_SEMANTIC_ENABLED=false` disables model inference; missing packages
or weights also fall back automatically. Model and threshold settings are documented
in `.env.example` without changing actual credentials.

## Migration, recovery and limits

Schema initialization adds five feature tables and indexes with `IF NOT EXISTS`.
SQLite foreign keys are enabled on connections; writes use transactions and content
fingerprints. Existing article/edition data is not rewritten. Before deploying against
valuable data, SQLite's backup API provides a consistent backup including WAL state.
Code rollback can leave the additive tables in place: the prior app ignores them.
No destructive schema rollback or production-data reset is needed.

Candidate memory reads the latest 300 reader observations; detail returns the latest
150 chronologically. Stable canonical URL membership is checked outside that bound.
Edition history for repetition is bounded to 30 editions. Saved continuing sections
contain at most three stories and three recent observations each. History bounds
trade recall for simple CPU-compatible operation.

Name cues are conservative capitalization heuristics, not trained named entity
recognition. Matching can miss paraphrases and long-running events, or still associate
different incidents sharing strong names/terms. Conflicting dates/numbers reject even
legitimate changes; false negatives are preferred over unsupported certainty. Text
differences are not factual changes. English-only model/heuristics and RSS excerpt
quality limit results. Global embeddings cache contains public source text vectors;
story/follow/profile queries are reader-scoped. Anonymous reader IDs remain the
existing localhost identity model, not public authentication.

## Files and integration

Added: `backend/news/embeddings.py`, `backend/news/story_graph.py`,
`frontend/src/components/story-timeline.jsx`, `tests/test_story_graph.py`,
`tests/fixtures/story_pairs.json`, `scripts/setup_story_model.py`,
`scripts/evaluate_story_graph.py`, `scripts/living_story_demo.py`, this report.

Updated: `.env.example`, `pyproject.toml`, `backend/config.py`,
`backend/news/store.py`, `backend/news/service.py`, `backend/news/ranking.py`,
`backend/news/routes.py`, `backend/news/pdf.py`, `frontend/src/main.jsx`,
`frontend/src/styles.css`, `ARCHITECTURE.md`, `FINAL_QA_REPORT.md`, `README.md`,
`docs/LIVING_STORY_GRAPH_PLAN.md`.

Likely overlap with other work: models/configuration, service, ranking, routes, PDF,
main React entry and shared stylesheet. No article model changes were needed. Changes
already reside in the requested main project; no worktree merge is needed. No new
commit hash exists. Review/test these local changes before any later commit or push.
