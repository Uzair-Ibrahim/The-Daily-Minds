# Optional Supabase Auth implementation

Implemented on 2026-10-17 in `.worktrees/supabase-auth`, branch
`feature/optional-supabase-auth`, based on `695adc5e7ea2dcb1b3a52c20ab0c0779f4fdb3dc`.
The initial implementation was isolated and uncommitted, with main unchanged.
The owner subsequently authorized merging and publishing this feature. No billing
activation, Supabase project creation or paid API call was performed.

## Delivered behavior

- Optional email/password signup, email-confirmation feedback, signin, device-local
  signout with attempted provider revocation, persistent sessions and SDK refresh.
- Editorial account strip and responsive login/signup dialogs. Loading and status/error
  feedback, an explicit Guest Mode option, bounded provider requests and locked account
  handling for expired sessions. Authentication is loaded separately from the guest app.
- FastAPI verifies ES256/RS256 signatures with project HTTPS JWKS, exact issuer,
  authenticated audience/role, UUID subject, required expiry/issuance and not-before.
  Forged, expired, incomplete, anonymous, wrong-project and service-role tokens are denied.
- Transactional, durable Supabase-subject to randomly allocated reader mapping.
  All private newspaper routes resolve authenticated identity from the verified token.
  Reader headers/query parameters cannot select another account. Guest requests to an
  account reader are denied even if optional authentication is disabled later.
- SQLite remains the application database. One additive table, `auth_readers`, is
  created with `IF NOT EXISTS`; existing tables and historical snapshots are retained.
  No existing main database was opened or migrated by these tests.
- Guest onboarding, Interest DNA, likes/saves, reading list, archives, image delivery,
  daily generation, PDFs, Living Stories, CLI and FastMCP interfaces are retained.
  Private API/image caching now includes Authorization and uses `no-store`.
  Frontend request chains stay bound to their original reading room while accounts
  switch; stale work cannot acquire the next account's authorization headers.

## Existing identity/schema audit and migration decision

The original client stores `daily-mind-reader`, a UUID used through `X-Reader-ID`.
Existing SQLite tables include profiles, articles, interactions, editions,
generation_leases, image enrichment, and Living Story state. Reader-scoped services
already check edition/article/story ownership; the missing security boundary was that
the incoming reader header was trusted. The new dependency resolves identity before
those checks and blocks anonymous access to account-owned UUIDs.

Existing guest data is preserved under its original UUID. Each signed-in account gets
its own profile/onboarding. There is **no silent claim or merge**, and guest-to-account
migration is deferred: a legacy guest UUID alone is insufficient proof of ownership.
Signout restores the same guest profile. Guest Mode continues to use the existing
local-demo capability model; it is not authenticated identity.

## Configuration and real-provider limitation

No Supabase URL or publishable key was configured in the inspected local environment.
No real Supabase signup, email delivery or hosted refresh-session revocation is claimed.
The real `.env` and existing provider credentials were not copied into this worktree.

Configure only these variables privately in your chosen checkout's ignored `.env`:

```dotenv
SUPABASE_AUTH_ENABLED=true
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
```

Use a **Free** project, enable Email/password and confirmation, configure your local
Site URL, and activate an asymmetric ES256/RS256 signing key. Do not provide a
service-role key, secret API key, signing secret or password. No billing is needed.
Follow [the complete setup/run guide](docs/SUPABASE_AUTH.md). It includes commands
for a separate localhost port and a separate SQLite file inside this worktree.

The [Free plan](https://supabase.com/pricing) and
[default email restrictions](https://supabase.com/docs/guides/auth/auth-smtp) were
checked against official documentation. Default email delivery is restricted to
authorized team recipients and rate limited; use a permitted demo address rather
than buying email delivery. No Supabase database schema or RLS changes are needed
because application data stays in SQLite.

## Actual verification

| Check | Result |
| --- | --- |
| Final full `python -m pytest -q` | 215 passed, 1 optional live Exa test skipped, 137.10 seconds |
| Final auth/image regression `pytest tests/test_auth.py tests/test_images.py -q` | 65 passed, 53.14 seconds |
| Final frontend `npm.cmd run build` | Passed, 3.50 seconds; lazy Supabase chunk, no chunk-size warning |
| Frontend `npm.cmd test` | 4 passed: account-switch isolation, refresh/scope, persistent cleanup, deadline |
| Credential pattern scan | No real credentials; one explicitly synthetic invalid-key fixture reviewed |
| Official SDK installation/dependency audit | Installed `@supabase/supabase-js` 2.118.0; npm reported 0 vulnerabilities |
| Python `pip check` | No broken requirements |
| `git diff --check` | Passed |
| Auth Chromium journey | Passed: 11 checks, zero uncaught browser errors, one cached JWKS fetch |
| Existing Guest Mode Chromium journey with real RSS | Passed: 6 checks, zero uncaught browser errors; 8-story paper, 3-page PDF |

An earlier full run found one expected regression assertion: the image test expected
only `Vary: X-Reader-ID`. It was updated to require both Authorization and X-Reader-ID;
the subsequent full suite passed. An initial auth fixture used an unsupported profile
field, and an initial browser offline step omitted its required email input. Both
test setup errors were corrected and their runs passed. The final frontend scope guard
initially exposed a missing API prop on the Living Story child component; the prop
was passed explicitly and the browser test now exercises its timeline/follow action.
No unresolved failure is hidden.

The auth security tests use ephemeral real RSA/EC signatures and mocked JWKS HTTP.
Coverage includes invalid signatures/algorithms/issuer/audience/roles, required claims,
expiry, future issuance/not-before, UUID validation, rotation/cache, stalled/offline
JWKS, single-fetch reuse, persistent mapping, configuration failure, reader-header and
query tampering, guest preservation, and isolation across all private route families.

The auth browser test uses synthetic accounts/news and mocked Supabase HTTP, with
real FastAPI, SQLite, Chromium and PDF rendering. It verifies signup confirmation,
signin/reload persistence, refresh of an expired stored token, account switching,
likes/saves/DNA/archives, a matching edition-ID PDF, signout restoring the guest,
API 401 locking, authenticated Living Story timeline/follow, failed provider logout
clearing local storage, failed signin feedback,
and a 390px mobile dialog. These are integration tests, not a live Supabase validation.

The separate existing browser journey used **real public RSS**, with credit search
disabled and an isolated database. It verified onboarding, feedback-driven changes
to scores/story order, PDF content, versioned archives, reload persistence, reset,
preferences and a 390px layout. No sample fixture was presented as real news.

Ignored local evidence:

- `artifacts/auth-secret-scan.json` (no real credential findings)
- `artifacts/auth-browser-results.json`
- `artifacts/auth-account-desktop.png`
- `artifacts/auth-mobile-signin.png`
- `artifacts/auth-account-a.pdf` (edition ID verified against its stored snapshot)
- `artifacts/browser-smoke.json`, `artifacts/browser-journey.webm`, existing guest screenshots/PDF

## Exact changed/new files

| Files | Purpose |
| --- | --- |
| `backend/auth.py` (new) | JWT/JWKS verification, persistent reader mapping, shared authorization dependency |
| `backend/auth_routes.py` (new) | Public safe config and authenticated account identity endpoints |
| `backend/config.py` | Optional Supabase settings, disabled by default |
| `backend/main.py` | Auth wiring and private response cache policy |
| `backend/news/routes.py` | Shared identity dependency on all private newspaper routes, image cache variation |
| `frontend/src/auth-client.js` (new) | Lazy official SDK, request identity, persistence cleanup and deadlines |
| `frontend/src/auth-room.jsx` (new) | Account/session lifecycle and editorial signup/signin screens |
| `frontend/src/main.jsx` | Auth wrapper, bearer headers, expired-session feedback, accurate privacy copy |
| `frontend/src/components/article-image.jsx` | Authenticated image metadata/byte requests |
| `frontend/src/styles.css` | Account strip and responsive editorial dialog styles |
| `frontend/package.json`, `frontend/package-lock.json` | Official Supabase browser dependency and lock |
| `pyproject.toml`, `requirements-lock.txt` | Explicit PyJWT crypto dependency; existing installed pinned version retained |
| `tests/test_auth.py` (new) | Mocked-provider security, authorization, timeout, configuration and persistence coverage |
| `tests/test_images.py` | Require Authorization-aware image cache headers |
| `frontend/tests/auth-client.test.mjs` (new) | Frontend account-switch, refresh, cleanup and deadline security tests |
| `scripts/auth_browser_smoke.py` (new) | Repeatable isolated Chromium/session/PDF integration |
| `.env.example` | Empty placeholders and opt-in flag; no credentials |
| `README.md`, `docs/SUPABASE_AUTH.md` (new), `docs/API.md`, `docs/ATTRIBUTIONS.md` | Setup, usage, security contract and attribution |
| `AUTH_IMPLEMENTATION_REPORT.md` (new) | This actual-results handoff |

## Remaining limitations

- Hosted Supabase behavior requires the owner's local configuration and live manual
  confirmation; Google OAuth, reset-password/account-deletion screens and guest
  migration are intentionally outside this minimal feature.
- Authenticated offline reading works while an unexpired token and fresh cached
  public signing key remain usable. After that, verification fails closed; Guest
  Mode and its saved local editions remain available through explicit selection.
- JWKS is cached locally for five minutes and also cached by Supabase's edge.
  Token verification does not perform an online session/ban lookup on each request;
  already-issued access tokens may remain usable until expiry after logout/deletion.
  There is no claim of instant global revocation. See
  [official signing-key guidance](https://supabase.com/docs/guides/auth/signing-keys).
- SPA sessions are kept in browser storage by the official SDK. HTTPS and protection
  against same-origin script injection are required for deployment beyond localhost.
- This is an optional hackathon integration, not an independent production security audit.

The owner subsequently authorized a normal Git commit, safe integration into main
and publication to the existing GitHub remote. The implementation-time test results
above are retained; publication is verified separately in the delivery response.
