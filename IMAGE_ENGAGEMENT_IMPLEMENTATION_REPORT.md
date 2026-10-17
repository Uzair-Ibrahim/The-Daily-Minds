# Image, engagement and editorial implementation report

Executed 2026-10-17. Branch `feature/news-images-engagement`; isolated worktree
`.worktrees/news-images-engagement` inside the existing project. Base commit:
`8838a0d7611462443bf256e7e524076fefb1be1b`. This task made no source edits to main or
the Living Story Graph worktree and merged neither. Concurrent graph changes appeared
in main during execution and were left untouched. A local feature commit is prepared only after passing tests;
the final handoff records its actual hash. No push, billing or paid API call occurred.

## Exact Dawn regression and root cause

Investigated the original article, not a substitute:
`https://www.dawn.com/news/2037770/millions-may-be-forced-to-move-as-climate-change-hits-south-asia-un`.

The actual RSS entry contains `media:content` and resolves to a real Dawn CDN WebP.
The existing image decoder accepted it and returned image bytes. An older real
`profile-B-edition.json` had **no image URL** for this article. The previous component
fetched an image only when the immutable snapshot already contained a URL, so legacy
editions could never discover available photography. RSS absence was not the cause.

Robots was accessible and allowed this path, but the publisher article page returned
**HTTP 403**. No anti-bot/paywall bypass was attempted. The fix uses the corresponding
publisher RSS item and does not need the blocked page. The image URL is discovered
from metadata; it is not hardcoded in application code.

The live browser now shows people carrying umbrellas through floodwater, and the same
photo appears in the actual PDF. The implementation stores resolved metadata in a
separate enrichment table; the original edition JSON remained byte-for-byte equivalent
as a parsed object before/after enrichment, engagement and PDF rendering.

Actual validated JPEG output: 85,989 bytes; SHA-256
`b5bd4c1701edfff914ca05de216ef7ef8d15e0dd998baafcbfd13bb4dfb8b6e7`.
Full source URL/provenance and execution evidence are in ignored
`artifacts/dawn-investigation.json` and `artifacts/image-engagement-smoke.json`.

## Image resolver, persistence and security

`ArticleImageResolver` prefers supplied image metadata; for missing legacy metadata it
looks up the **same article URL** in the known publisher feed. Page fallback, when
needed, checks robots and fetches only known public publisher hosts. It parses Open
Graph, Twitter image tags and `NewsArticle.image` structured data; a conflicting
canonical page is rejected. Google News intermediaries are not decoded or guessed.

RSS priority is media content, thumbnail, image enclosure, entry image extension, then
description/content HTML. Existing public extraction interfaces are retained. New
optional article fields include `image_source`, `image_alt`, `image_status` and
`primary_topic`; existing `image_url`, `image_origin` and credits remain compatible.
Enrichment adds association, reason, resolution time and an explicit permission caveat.
Old snapshots are not rewritten. Enrichment metadata and positive/negative decisions
survive restart through an additive SQLite table keyed by article ID and publisher URL.

Actual image decoding checks format, MIME, dimensions, aspect ratio and size. Tiny,
tracking, logo, sprite, placeholder, icon/data and unsupported URLs fail safely.
The server accepts image destinations only on the existing audited publisher CDN
allowlist and only for reader-owned edition articles. The endpoint accepts IDs, not an
arbitrary proxy URL. Image redirects remain rejected. Publisher-page redirects are
bounded and revalidated on every hop; private, credentialed, HTTP downgrade, unknown
host and nonstandard-port targets are rejected.

The HTTP transport resolves DNS at connection time, rejects any non-public address
and connects to the vetted numeric IP. HTTP Host/TLS hostname remain the publisher's
original hostname and TLS verification remains enabled. Thus the socket cannot silently
resolve the hostname a second time to a private target. Environment proxies, application
keys and browser cookies are not forwarded. Tests cover IP pinning and private redirects.

Image loading is bounded by existing byte/pixel/time limits, three image slots and a
16-task cap. Metadata enrichment has eight in-flight slots, a 16-second overall deadline,
two page slots and per-publisher serialization. Page requests are separated by at least
two seconds and honor a larger robots crawl delay. Feeds cache for three minutes and
robots for an hour. Failed enrichment and image delivery cache for five minutes;
successful metadata/images cache for 24 hours. Disk JPEG caching uses hashed URLs,
atomic writes and a 64-record bound. Restart checks reused both metadata and bytes
with **zero new outbound requests**.

No image license is invented. `image_permission` explicitly states that independent
reuse permission is unverified. RSS-provided references and available credits are
preserved for the local reader. This is not a legal determination that all publisher
photos are licensed for public redistribution; no universal coverage is claimed.

## Actual discovery coverage and performance

Latest feed audit at approximately 09:54:30 UTC:

| Feed | Entries | Image metadata observed |
|---|---:|---|
| BBC World | 27 | 27 thumbnails |
| Dawn | 23 | 23 media-content images and thumbnails; one HTML-image entry |
| Guardian World | 45 | 45 media-content entries, including size alternatives |
| BBC Technology | 21 | 21 thumbnails |
| BBC Science | 42 | 42 thumbnails |
| BBC Sport | 75 | 75 thumbnails |
| Google News English/Pakistan query `AI` | 100 | No image fields |

These are metadata counts from actual responses, not guarantees every asset is reusable
or currently downloadable. `scripts/audit_feed_images.py` reproduces the audit.

The combined isolated Dawn proof and existing full browser journey accumulated 167
unique real normalized candidates; 143 had RSS image metadata (**85.6% of that captured
set**). This is neither an all-publisher coverage claim nor an image-delivery success
rate. The primary proof displayed two actual photographs and one compact text fallback.

The latest primary retrieval returned its bounded 150-candidate batch in **4.509s**.
The specific Dawn item was also present in the fetched source-feed cache when excluded
from the global candidate cap; the harness selected that genuine item for the controlled
regression rather than inventing content or changing production ranking limits.

Across reloads, sharing, PDF and archive navigation, the primary browser proof made
14 **local** image/metadata requests. The backend made **one metadata/feed request**
and **zero asset requests** in this warm-cache run. The image had already been genuinely
downloaded and validated in the initial trace/cold proof. Counts exclude the separate
full-user-journey regression and later seven-feed audit. Metadata enrichment is lazy
for secondary stories and limited to displayed image positions; generation does not
fetch all article pages. No Exa, Tavily, model or paid image call was made.

## Editorial classification

The description mentions technology and government action, so existing multi-topic
matching returned technology/world/science. React displayed `topics[0]`, whose order
followed the topic dictionary, not the headline's primary subject. It did not inherit
the reader's profile, but the result was still misleading.

`editorial.primary_topic` prioritizes headline topic evidence for display. The Dawn
story now says **Science & Discovery** on the webpage and science in PDF. Existing
ranking weights, feedback math and multi-topic relevance are preserved. New ingestion
stores the primary topic; legacy display sections are returned separately from stored
article snapshots. Tests cover climate, technology, world, science and business.
This is a bounded keyword heuristic, not a semantic classifier or universal accuracy claim.

## Like/unlike, save/unsave and Interest DNA

The existing `interactions` table remains authoritative. The interaction endpoint now
accepts explicit `active` state (default true for compatibility). One unique active
record per reader/article/action prevents duplicates. Deactivating a like removes
only that like; saves stay independent. Saving/unsaving uses the same mechanism.
Repeated desired-state requests are idempotent. Stable article identity persists across
edition versions and restart; editions are never counted as separate likes.

Actual browser actions passed Like → Unlike → Like and Save → Unsave → Save, refresh,
cross-edition identity and independent save state. Counts visibly changed **0 → 1 → 0
→ 1**. They are labeled **YOUR LOCAL LIKE**, not worldwide publisher engagement.
Reader APIs and reading lists remain isolated by the existing anonymous reader ID;
this introduces no public authentication system.

DNA and ranking both read the same active interaction rows. Removing a like/save
reverses exactly its contribution. Capped displayed weights match ranking components;
skips retain their existing behavior. Historical edition DNA snapshots remain unchanged.
The new Reading list exposes persisted saved stories and their original edition/source.
Reset feedback retains existing semantics: it clears active feedback, including saves.

UI state changes after acknowledgement; simulated HTTP 503 left the prior like state
intact. Reload and the next acknowledged desired-state request reconcile with persistence.
An offline client cannot know whether a timed-out request committed until it reconnects.

## Sharing

Every story has a keyboard/mobile-accessible share group with WhatsApp, X, LinkedIn,
Copy link and native-device sharing. URL parameters use `URLSearchParams`. Public source
URLs and headlines are used; localhost/reader/session URLs are not manufactured or
included. Google intermediary URLs remain intermediary URLs rather than guessed originals.
External share anchors use `noopener noreferrer`; no third-party request occurs merely
by opening the menu. The browser check observed none before selecting a share action.

Copy success, unsupported Clipboard API, native-share payload, unsupported Web Share,
Escape/focus handling and manual selectable-link fallback were exercised. Native and
clipboard APIs were deliberately stubbed for deterministic browser verification; no
message/post was sent to another person or social network. Real external anchor URLs
were checked without sending a post. Unit tests verify encoding and private-URL rejection.

## Web/PDF results and actual tests

The cream/dark-green masthead and newspaper hierarchy remain. Lead and selected
secondary images use aspect-preserving frames and source credits. Noncritical images
use intersection-based lazy loading. Missing photos now use a compact typographic
treatment (measured below 80px in the test), with no large empty photograph container.
Alt text uses supplied metadata, or the source-associated headline when no caption exists.

The genuine Dawn photograph was visible in the actual Chromium browser screenshot.
The matching **two-page PDF** contained one embedded publisher image, original title,
edition ID and links; no clipping or distortion was found in visual inspection. PDF
uses the separate enrichment overlay without changing the saved edition. Secondary
photos remain web-only to protect A4 pagination. Failed images retain a valid text PDF.

| Executed check | Actual result |
|---|---|
| Clean baseline full suite | 154 passed, 1 optional skipped in 75.40s |
| Image/engagement/newspaper targeted run | 64 passed in 11.30s |
| Expanded full suite before final priority test | 169 passed, 1 optional skipped |
| Final full suite | **170 passed, 1 optional skipped in 114.12s** |
| Final `npm.cmd run build` | PASS, Vite 7.3.7, 1,585 modules, 4.18s |
| `python scripts/image_engagement_smoke.py --full-journey` | PASS: genuine Dawn/secondary photos, compact missing image, all engagement/share checks, PDF, mobile and original full browser journey |
| Existing full journey | PASS: onboarding, actual RSS, like/save/skip, next-version order changes, archive/reload, reset/preferences and mobile; three-page eight-story PDF |
| `python -m pip check` | No broken requirements found |
| `python -m compileall -q backend tests scripts` | Exit 0 |
| `git diff --check` | PASS |
| Source security scan | 100 files checked; zero configured-secret or credential-pattern matches; environment files excluded |

The one skipped pytest is the opt-in live Exa test. Test fixtures never stand in for
the genuine-image proof. Existing tests were preserved. Initial harness issues were
corrected: selecting the actual target from its source feed when globally capped,
scrolling before asserting lazy-loaded secondary images, and handling uppercase section
text in assertions. A regression initially caught duplicate loader calls; the resolver
now shares its validated bytes instead of immediately loading them again.

An automatic approval-review attempt was temporarily blocked by a usage-limit error,
not a safety determination. After the user reported the reset, the blocked verification
was rerun successfully. No approval restriction was bypassed.

## Browser evidence (ignored local artifacts)

- `artifacts/engagement-dawn-hero.png`: genuine floodwater photo, secondary photo and section label.
- `artifacts/engagement-liked.png`, `engagement-unliked.png`, `engagement-liked-again.png`.
- `artifacts/engagement-saved.png`, `engagement-unsaved.png`, `engagement-saved-again.png`.
- `artifacts/engagement-share-menu.png`: working share controls.
- `artifacts/engagement-mobile.png`: actual 390px newspaper.
- `artifacts/engagement-dawn-paper.pdf`, `engagement-pdf-1.png`, `engagement-pdf-2.png`.
- `artifacts/image-engagement-smoke.json`: actual browser results and network counts.
- `artifacts/image-feed-audit.json`, `dawn-investigation.json`: actual source inspection.
- `artifacts/browser-smoke.json` and browser journey artifacts: existing regression.

The photo, mobile page and both PDF pages were visually inspected. Test clicks are
automation evidence, not organic readership. No API key, local reader database, photo
binary, recording or browser screenshot is included in the source commit.

## Files and integration handoff

Created:

- `backend/news/image_resolver.py`: persistent legacy-image enrichment and permitted page fallback.
- `backend/news/safe_network.py`: DNS-pinned connection transport.
- `backend/news/editorial.py`: independent headline section selection.
- `frontend/src/components/article-engagement.jsx`: reversible controls, local count and sharing.
- `frontend/src/components/share-links.js`: pure encoded sharing URL builder.
- `tests/test_image_engagement.py`: engagement, DNA, extraction, persistence and network tests.
- `scripts/image_engagement_smoke.py`: controlled real source/browser/PDF proof.
- `IMAGE_ENGAGEMENT_IMPLEMENTATION_REPORT.md`: this handoff.

Shared files modified:

- `backend/news/models.py`: optional metadata/section fields and desired-state input.
- `backend/news/discovery.py`: additional source metadata and primary section at ingestion.
- `backend/news/images.py`: persisted byte cache, format/aspect checks, extraction order and safe transport.
- `backend/news/store.py`: additive enrichment table, active desired-state records and reading list.
- `backend/news/routes.py`: image metadata enrichment, feedback state, reading list and PDF overlay.
- `backend/news/pdf.py`: primary section and compact no-image treatment.
- `frontend/src/components/article-image.jsx`: enrichment, lazy loading and compact fallback.
- `frontend/src/main.jsx`: wire controls, state refresh, reading list and section labels.
- `frontend/src/styles.css`: restrained engagement/share/compact-image styling.
- `pyproject.toml`: explicit existing `httpcore>=1.0,<2` runtime dependency for pinned transport.
- `README.md`, `docs/API.md`: usage and additive contracts.

No lock versions changed: installed/locked HTTPcore and Pillow already satisfy the
manifest. Existing installed frontend packages were reused through an ignored local
dependency junction; no dependency installation or purchase was required. All runtime
data and test ports were isolated. No `.env` was copied into the feature worktree.

Expected integration conflicts are the shared files above, particularly models, routes,
store and `frontend/src/main.jsx`. Keep image enrichment separate from Living Story Graph
membership; do not replace graph routes or mutate graph/edition snapshots. Preserve the
old default `active=true` interaction contract. New article response overlays are
`article_sections` and `article_engagement`, leaving the stored `articles` payload intact.
Merge/cherry-pick and public push require the owner's separate approval; none were done.
At handoff, main contains concurrent uncommitted graph-related changes, including routes,
store, PDF, ranking/service/configuration, frontend, dependencies and new graph/model
helpers/tests. They were not staged, reset or copied into this branch. The 170-test result
applies to this isolated worktree at the recorded base plus this feature, not an untested
combined integration with those concurrent edits. Review integration before applying it.

## Remaining limits

- Publisher-page access and licensing vary. Dawn page access was 403, honored; its
  RSS photo worked. Generic OG/Twitter/structured fallbacks are tested with mocked
  responses, not claimed as live successful page retrieval for that blocked Dawn URL.
- No independent reuse-license audit was completed. Unknown/restricted sources must
  remain unasserted; do not infer redistribution rights from metadata availability.
- BBC thumbnails can be small; no fake high-resolution URLs, guessed Google canonical
  URLs or unrelated photography are generated. CDN/page allowlists remain deliberately narrow.
- One best RSS candidate is selected; a broken candidate may need page fallback and
  does not trigger unlimited alternative image downloads. Huge/unsupported/odd-aspect
  assets fall back cleanly. Page metadata can still be missing or publisher-generic.
- Persistent image cache is bounded to 64 records; new assets beyond that bound use
  memory caching. Assets can disappear/change, and stale/expired assets need network
  validation. This is not a permanent photographic archive or a public image service.
- Primary section selection is a headline keyword heuristic. Ambiguous headlines are
  not guaranteed to be classified correctly. Ranking behavior otherwise stays intact.
- Likes are this reader's active 0/1 count, not global social popularity. Anonymous IDs
  provide local partitioning, not production authentication. Multi-tab state refreshes
  on reload/acknowledged actions, not real-time broadcasts.
- No social-network message was sent, public deployment performed, branch merged or
  pushed. Existing event-start/monitored-commit compliance and Loom blockers remain.
