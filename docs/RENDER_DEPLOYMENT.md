# Render Free with durable Supabase storage

**Live:** https://the-daily-mind.onrender.com

Render service `srv-db9n1vdg1s2s739anspg` is deployed on the verified **Free** plan.
Deployment `dep-db9n1vtg1s2s739anu30` built and served commit
`839b8a2bbba83728ad8c633dadf7ca428807630f`. The owner explicitly approved transferring
only the database connection and Supabase Auth configuration to this service. No
Exa/Tavily/LLM keys were transferred, no billing was activated, and the existing
unrelated Render service was not modified. No local private database was uploaded.

The official Render CLI 2.29.0 was installed with WinGet (`Render.CLI`) and its official
browser login completed. Workspace selection is saved in the CLI's local configuration.

## Storage decision

The owner rejected ephemeral SQLite on Render Free and selected existing Supabase
Free Postgres for the cloud, with local SQLite retained as the default. The app now
supports explicit `DATABASE_BACKEND=postgres` plus a private `DATABASE_URL`. Missing
credentials fail closed; cloud mode does not silently fall back to temporary SQLite.
Local `DATABASE_BACKEND=sqlite` remains unchanged, even when a cloud URL is saved.
Existing SQLite files are neither copied to the cloud nor deleted.

Render Free cannot attach a persistent disk and loses local filesystem changes on
restart, redeploy and spin-down. Supabase stores committed app records separately
from Render. Free providers still have quotas, idle pausing and cold starts; no
unlimited uptime or storage guarantee is implied.

## Configure the database password privately

The project URL/publishable key configure Auth and client Data API access. They are
not PostgreSQL connection credentials. Use the database password originally chosen
for the Supabase project, not your Supabase login password or a publishable API key.

From your own PowerShell terminal in the project directory:

```powershell
.\.venv\Scripts\python.exe scripts/configure_cloud_database.py --host aws-0-ap-southeast-1.pooler.supabase.com
```

Enter the database password at the hidden prompt. The helper percent-encodes special
characters, verifies TLS and `SELECT 1`, and saves the URL to ignored `.env` only on
success. Do not send the password/URI in chat. Local SQLite mode is not switched.
The host above is the Session pooler host supplied by the owner; use your own exact
Supabase Connect host if using a different project.

The connection uses `sslmode=verify-full` and the official public Supabase root CA,
bundled as `backend/certs/prod-ca-2021.crt`. Its download URL is taken from Supabase
Studio's official `ssl:certificate_url` configuration. SHA-256 of the downloaded file:
`700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`.
This is a public CA certificate, not a private key. Database TLS verification remains
enabled. Download provenance:
[official Studio configuration](https://github.com/supabase/supabase/blob/master/apps/studio/hooks/custom-content/custom-content.json),
[SSL guidance](https://supabase.com/docs/guides/platform/ssl-enforcement).

## Cloud runtime and safety

`Dockerfile` builds the existing React/Vite app using Node 22, then runs FastAPI on
Python 3.12 with Chromium and its Linux libraries for PDFs. It runs as an unprivileged
user, binds Render's `$PORT`, and uses one worker. Optional local embedding weights
are omitted to fit Free memory; conservative Living Story matching remains available
and labeled. Paid search stays disabled. The build context excludes `.env`, credentials,
local databases, environments, artifacts, worktrees and dependencies.

`render.yaml` explicitly selects `plan: free`, Docker, Singapore and `/health`.
Automatic deploys are off. Required runtime configuration is entered privately:

```dotenv
DATABASE_BACKEND=postgres
DATABASE_URL=
DATABASE_SCHEMA=daily_mind
SUPABASE_AUTH_ENABLED=true
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
STORY_SEMANTIC_ENABLED=false
CREDIT_SEARCH_CONFIRMED_FREE=false
LLM_PROVIDER=none
```

The adapter retains the existing Store interface and translates only its bounded SQL
vocabulary: JSON article extraction, conflict handling, timestamp precision, scalar
min/max and transaction locks. Psycopg binds parameters; values are not interpolated
into SQL. A private `daily_mind` schema keeps app tables out of the public Data API.
Transactional advisory locks preserve reader allocation, generation leases and stable
edition versions across connections. Queries, lock waits, pool size and connects are
bounded. Database errors use the existing generic 503 storage handler.

The cloud starts with its own application data; no private local profiles/archives
are uploaded automatically. After deployment, set the public HTTPS URL in Supabase
Auth Site URL/allowed redirects so confirmation emails return to the deployed app.

## Actual verification so far

- Render CLI installed and login successful.
- Render CLI blueprint validation: `valid: true`, one Free web service planned.
- Final complete regression with real Postgres enabled: 225 passed, 1 optional
  Exa live test skipped, 189.18 seconds. A fresh workspace test directory avoided
  a Windows temp-directory permission error encountered on the first attempt.
- Focused adapter/helper unit tests before live setup: 7 passed, 3 cloud tests skipped.
- Frontend security tests: 4 passed. Production Vite build passed in 3.46 seconds.
- Python dependency check and whitespace check passed. Configured-secret scan: no findings.
- TLS reaches the supplied pooler and validates with the official Supabase CA.
- Password authentication verified with TLS after owner ran the private setup helper.
- Real Postgres adapter/integration suite: 10 passed in 61.00 seconds.
- Real cloud tests verified durable profiles/editions/account mappings, rollback,
  reader isolation, JSON reading lists, Living Story follows and generation leases.
  Only disposable QA schemas were created and removed.
- Actual Linux Docker build on Render succeeded, including Vite, Python packages,
  the public CA and Chromium with Linux libraries. Offline local wheel packaging
  also verified that the public CA certificate is included.

To repeat cloud verification, run the opt-in cloud tests in disposable private
QA schemas (never the production schema), then build/deploy and verify the public
webpage, RSS generation, PDF and edition persistence after a Render restart:

```powershell
$env:RUN_POSTGRES_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_postgres.py -q
Remove-Item Env:RUN_POSTGRES_TESTS
```

The live tests create and remove only newly allocated `daily_mind_qa_<uuid>` schemas.
They use explicitly synthetic test-only news isolated from production fallback content.
No deployment success or live persistence test is claimed until these checks run.

References: [Render Free](https://render.com/docs/free),
[Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Supabase Free quotas](https://supabase.com/pricing).

## Public deployment and restart results

All checks below ran against the live HTTPS site, not localhost or mocked APIs.

- `/health`: HTTP 200; configured Auth endpoint: HTTP 200 with Auth enabled.
- Real RSS Chromium journey: PASS, 8 stories, onboarding, likes/saves/skips,
  explainable DNA, versioned archive/reload, feedback reset and preferences.
- Matching PDF: 3 pages; exact edition ID, date and every visible story title verified.
- Responsive 390px layout: no horizontal overflow; zero uncaught browser errors.
- Living Story detail/follow persisted; another reader's edition request returned 404.
- Repeated same-day generation returned the existing edition ID.
- Public Data API roles `anon` and `authenticated` have no usage on the app schema.
- An actual Render restart replaced instance `...-855rp` with `...-dcrx2`.
  Both complete saved edition responses, profile and archive remained identical.
  The followed story remained followed. The same saved edition exported as a
  matching 3-page PDF after replacement, and its webpage reopened with all 8 titles.

The browser harness was corrected for two real-data assumptions without altering
product ranking or publisher text: feedback must change priority scores, but cannot
promise a visible order change on every news set; PDF title comparison ignores
invisible Unicode formatting omitted by PDF extraction. This run changed scores
and retained visible order. Exact edition ID comparison was strengthened as well.

Ignored local evidence: `artifacts/browser-smoke.json`, `artifacts/daily-mind-live.pdf`,
`artifacts/render-service.json`, `artifacts/render-persistence-results.json`,
`artifacts/render-after-restart.pdf`, `artifacts/render-final-browser.json`,
`artifacts/render-after-restart-desktop.png` and `artifacts/render-after-restart-mobile.png`.
No reader checkpoint, runtime database, screenshot or credential was committed.

Automatic Git deploys are disabled. Later documentation/browser-harness commits do
not change the running application build unless explicitly deployed. Source for the
running app is the deployment commit recorded above.

## Remaining account setup and limits

Set Supabase Authentication ? URL Configuration ? Site URL and allowed Redirect URL
to `https://the-daily-mind.onrender.com` so confirmation emails return to the live app.
A live signup/email-confirmation/login round trip was not performed; it needs the
owner's actual email confirmation. Existing auth signature/security tests passed,
and the public signin form was verified. Do not treat the publishable API key as a
Postgres password.

Free Render may sleep and cold-start. Daily background checks run while awake;
startup/on-demand catch-up remains supported. Supabase has Free quotas and inactivity
pausing. Optional MiniLM embeddings are disabled on this Free deployment; conservative
Living Story matching remains labeled and was verified. Publisher image bytes are
cached ephemerally and may be retrieved again after restart; snapshots, source
metadata, accounts, editions, interactions and follows are in durable Postgres.
