# Editorial image support — actual implementation and QA

Verified 2026-10-17. Existing FastAPI/FastMCP/CLI, daily scheduler, ranking, archives,
feedback and newspaper styling were extended in place. No paid API, image generation,
article-page scraping, cloud image service, Git commit or push was performed.

## Audit findings

Previously `Article` had no image fields, RSS ingestion stripped descriptions to plain
text, saved editions contained text/provenance only, React rendered text, and PDF blocked
all remote requests. JSON-based article/edition persistence supports additive metadata
without a database migration. Older edition snapshots remain unchanged.

The actual feed audit ran at approximately **09:08:53 UTC**. Counts cover all entries
in the responses, while ordinary ingestion retains its existing 30-entry/feed limit.
These are observed responses, not permanent guarantees about future feed contents.

| Current feed | Entries inspected | Image fields observed | Usable delivery verified |
|---|---:|---|---|
| BBC World | 27 | `media_thumbnail`: 27; supplied size 240×135 in sampled entry | Yes, actual sample JPEG fetched and validated |
| Dawn home | 24 | `media_content`: 24; `media_thumbnail`: 24; HTML `img`: 1; sampled content 800×480 | Yes, actual sample WebP decoded/re-encoded |
| Guardian World | 45 | `media_content`: 45; sampled alternatives 140/460/700px | Yes, largest sampled 700px image fetched |
| BBC Technology | 21 | `media_thumbnail`: 21; sampled width 240px | Yes, actual sample PNG decoded/re-encoded |
| BBC Science | 42 | `media_thumbnail`: 42; sampled width 240px | Yes, actual sample JPEG fetched |
| BBC Sport | 75 | `media_thumbnail`: 75; sampled width 240px | Yes, actual sample JPEG fetched |
| Google News search (`AI`, English/Pakistan) | 100 | No media content, thumbnail, enclosure, image or HTML image fields | No image supplied; section fallback |

No current audited feed exposed image enclosures or an entry-level `image` field in
these responses. Those shapes are supported and tested. One sample asset per image-
bearing feed was actually downloaded successfully; not every asset was fetched. Exact
feed URLs, source image URLs, observed counts, timestamps and sample byte sizes are in
ignored `artifacts/image-feed-audit.json` and `artifacts/image-support-smoke.json`.
Reproduce with `python scripts/audit_feed_images.py`.

## Extraction, persistence and delivery

Extraction priority is media content, media thumbnail, image enclosure, first valid
HTML image from description/content, then entry-level image metadata as a final fallback.
Larger candidates win within media groups. Relative URLs resolve against the article;
lazy `data-src` is supported. Source query strings, including publisher CDN signatures,
are retained. No guessed high-resolution URLs or unrelated stock images are substituted.
No optional Open Graph fetch was needed or implemented.

New `Article` and edition JSON fields are `image_url`, `image_origin`, `image_credit`.
Missing fields default safely. Extraction runs before existing HTML-to-plain-text
description normalization. Invalid/missing images do not discard their article.
Image metadata is already propagated by ranking/storage without schema rewrites.

Only HTTP/HTTPS candidates survive. Data/script/file URLs, URL credentials, private IPs,
nonstandard ports, obvious trackers/logos/sprites and SVG/GIF/icon URLs are rejected.
Known tiny metadata/query dimensions are rejected. Delivery additionally verifies the
actual raster dimensions, MIME type and decoded format: JPEG/PNG/WebP, at least
160×90px and no more than 20 million pixels. Received data is capped at 3 MB.

The reader-scoped image endpoint accepts edition/article IDs, never an arbitrary URL.
Only the saved URL on the exact audited hosts `ichef.bbci.co.uk`, `i.dawn.com` and
`i.guim.co.uk` can be fetched. DNS must resolve to public addresses; redirects and
environment proxies are disabled. No application keys, browser cookies or reader IDs
are forwarded to the publisher. Third-party image requests happen on the backend;
the browser uses same-origin blobs with its existing anonymous reader header.

Downloads have a six-second overall deadline, four-second HTTP timeout, three download
slots and at most 16 in-flight URL tasks. Concurrent identical requests coalesce.
Validated pixels are resized within 1280×1000 and JPEG-encoded without source EXIF;
output is capped at 1.5 MB. The 32-entry in-memory cache retains successful images for
24 hours and failures for five minutes. Unavailable delivery returns an empty 204;
the frontend renders a section treatment, never a broken image icon.

## Final web/PDF behavior

- The lead receives a prominent image; the next two stories receive medium images.
  Later stories keep the established text-first newspaper grid. Typography, colors,
  masthead, ranking details, source links and feedback controls are preserved.
- Image frames use aspect-preserving `contain` rather than distorting/cropping news
  photography. Desktop and 390px mobile layouts passed overflow checks.
- Loading shows a restrained section treatment. Missing/unavailable photos show section
  typography and “Publisher image unavailable”, explicitly not substitute photography.
- Supplied image credits are retained. Where absent, captions say “Image via [source]”;
  photographer identity and licensing are never invented. Publisher/source rights remain.
- PDF embeds **only the lead image**, using the same validated cache/loader. This keeps
  the existing two-column print layout manageable. Remote Chromium requests remain
  blocked; validated image bytes are embedded as a data URL before rendering.
- PDF failures/timeouts fall back to a section treatment with unchanged story content.
  `/print` remains a self-contained text/section-treatment preview. Web and PDF retain
  the same saved titles, text, IDs, URLs and timestamps; secondary photos are web-only.
- Old archives do not gain metadata retroactively. Existing snapshots, including
  offline editions and explicit versions, remain immutable and readable.

## Executed validation

| Command/check | Actual result |
|---|---|
| Initial image/newspaper targeted run | 45 passed, 2 test-setup errors: pytest generated enormous Windows test IDs from binary payloads; fixed by explicit short case IDs |
| Corrected initial image tests | 30 passed in 5.97s |
| Initial complete suite | 151 passed, 1 optional skipped in 70.04s |
| Final complete suite | **154 passed, 1 optional skipped in 77.53s**, no failures |
| `npm.cmd run build` | PASS, Vite 7.3.7, 1,583 modules, 2.48s |
| `python scripts/image_support_smoke.py --full-journey` | PASS twice; latest run refreshed the complete feed audit |
| `python scripts/daily_generation_smoke.py` after image support | PASS: actual automatic RSS edition, stable same-day reuse, web/PDF/archive, simulated offline RSS fallback and unchanged historical snapshot across restart |
| Actual real-image web/PDF | PASS: lead image decoded on webpage, one embedded photo in two-page PDF, every saved article title and edition ID matched, hyperlink annotations present |
| Simulated image HTTP failure | PASS: explicit 204 simulation showed category fallback with no broken `<img>` |
| Legacy/no-image frontend | PASS: QA-only copy of real retrieved content with image fields removed remained readable with section treatments |
| Existing full browser journey | PASS: onboarding, real RSS, like/save/skip, changed ranking/order, versioned archive/reload, reset/edit/cancel, PDF and mobile |
| `python -m pip check` | No broken requirements found |
| `python -m compileall -q backend tests scripts` | Exit 0 |
| `git diff --check` | PASS |
| Working-source security scan | 92 files checked; no configured-key/private-key matches; `.env` excluded |

The skipped Exa test is opt-in. All actual image smoke servers used isolated databases,
empty provider keys and no credit-based search. The existing user server/data were not
stopped or replaced. Owned QA servers shut down after execution. Solid-color images
exist only as explicitly marked unit-test fixtures; product proof used actual CDN bytes.
Existing tests were preserved. Coverage includes metadata/HTML extraction, malformed
URLs, tracking/tiny images, persistence, invalid/oversize payloads, redirects, private DNS,
timeouts, coalescing, negative caching, access scoping, real PDF embedding and fallback.

Latest proof edition: `893a4671-f921-48bb-9364-faca8d80f52d`. Its original JSON snapshot
was identical before/after browser interaction, image delivery and PDF export. Both
browser journeys reported zero page errors. Full existing journey used eight stories
and a three-page PDF, with actual automated feedback moving selections from 3→2 and
6→4. These are QA interactions and ranking positions, not organic engagement metrics.

## Screenshots and local artifacts

- Before: `artifacts/image-before-web.png`, copied from the earlier real no-image daily
  proof. It is a different captured edition/profile, not a controlled same-story image
  toggle or a claim that news content stayed constant between captures.

Open [before](artifacts/image-before-web.png), [after desktop](artifacts/image-after-desktop.png),
[after mobile](artifacts/image-after-mobile.png), or [the actual image-bearing PDF](artifacts/image-supported-paper.pdf).

- After desktop: `artifacts/image-after-desktop.png`.
- After mobile: `artifacts/image-after-mobile.png`.
- Failed photo fallback: `artifacts/image-unavailable-mobile.png`.
- Legacy/missing metadata: `artifacts/image-legacy-no-photo.png`.
- Actual PDF: `artifacts/image-supported-paper.pdf`.
- Rendered pages: `artifacts/image-pdf-page-1.png`, `image-pdf-page-2.png`.
- Source-only recovery checkpoint: `checkpoints/before-image-support.zip`.

Desktop/mobile and both PDF pages were visually inspected: editorial styling remains,
photos are aspect-preserving, attribution is visible and no article text was clipped.
All local image/PDF/audit artifacts stay ignored; none were uploaded or committed.

## Exact source/document files changed in this image task

| File | Change |
|---|---|
| `backend/news/images.py` | Extraction, URL/dimension checks, verified raster processing, bounded safe delivery/cache |
| `backend/news/models.py` | Optional image metadata and nonfatal URL validation |
| `backend/news/discovery.py` | Extract image metadata from each RSS entry |
| `backend/news/routes.py` | Reader-scoped image endpoint; shared loader for PDF |
| `backend/news/pdf.py` | One embedded lead photo, credit, bounded loading and fallback |
| `frontend/src/components/article-image.jsx` | Blob loading, loading/success/fallback rendering and cleanup |
| `frontend/src/main.jsx` | Connect edition IDs and editorial images to first three stories |
| `frontend/src/styles.css` | Editorial image frames/captions/placeholders and mobile sizes |
| `pyproject.toml` | Promote existing Pillow dependency to runtime |
| `tests/test_images.py` | Image extraction, delivery, persistence, scoping and PDF tests |
| `scripts/audit_feed_images.py` | Reproducible actual feed metadata audit |
| `scripts/image_support_smoke.py` | Real CDN/browser/mobile/PDF and existing-journey proof |
| `README.md`, `ARCHITECTURE.md`, `docs/API.md`, `docs/ATTRIBUTIONS.md` | Usage, flow, endpoint and image attribution/limits |
| `FINAL_QA_REPORT.md`, `IMPLEMENTATION_STATUS.md`, `IMAGE_SUPPORT_REPORT.md` | Actual current results and limitations |

`requirements-lock.txt` already pins Pillow 13.0.0 and needed no version change. No
dependency download was necessary. Prior uncommitted daily-generation changes were
preserved; they are separately documented in docs/DAILY_GENERATION_QA.md. `.env` was
not changed. No Git history, staging, commits or remote publication were modified.

## Known limitations

BBC supplies small 240px thumbnails; they may look soft at hero size. No higher-quality
variant is guessed. Google News results often have no image. Unknown future image hosts
and redirected assets fall back until explicitly audited; no Open Graph crawler is added.
The first valid metadata URL is used; there is no expensive second-choice retry/crawl
after an asset fails. Credits can be missing or incomplete in publisher metadata.

Metadata inclusion is not proof of redistribution rights; no image licensing audit or
new license grant is claimed. Original publisher/source rights and supplied credits are
retained. This remains a local reader rather than a licensed image syndication service.

Only URLs/credits are persisted. Cached image bytes are memory-only, can change or
vanish at the publisher, and are unavailable offline after a cold restart. Text/date/
version snapshots remain immutable even when an image must fall back. Image cache is
per process. PDF photo placement is not guaranteed on page one for unusually long
lead stories; preserving all article text takes priority over fixed page counts.
No additional ranking bias toward image-bearing stories was introduced.
