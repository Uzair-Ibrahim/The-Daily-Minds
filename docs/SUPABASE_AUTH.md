# Optional Supabase authentication

Guest Mode needs neither a Supabase account nor internet access to Supabase.
Authentication uses Supabase Auth only; application profiles, feedback, editions,
archives, images and Living Stories remain in the existing local SQLite database.

## Configure locally without sharing credentials

1. Create/select a **Free** Supabase project in a Free organization. Do not activate
   billing, paid add-ons, custom domains or an upgraded plan. No project was created
   by this implementation. See [Free plan](https://supabase.com/pricing).
2. Enable the Email/password provider in Authentication. Keep email confirmation
   enabled. Configure Site URL to your local app, for example
   `http://127.0.0.1:8002`. After confirming by email, return to the app and sign in;
   this implementation deliberately does not consume sessions from URL fragments.
3. In JWT Signing Keys, use an active **asymmetric ES256 or RS256** signing key.
   Legacy HS256 tokens are rejected. Follow the official
   [signing-key migration instructions](https://supabase.com/docs/guides/auth/signing-keys)
   if the project still uses HS256. Never copy a JWT secret into this application.
4. Put the project URL and **publishable** `sb_publishable_...` key into `.env`
   **inside the checkout you are running**, using these variable names:

   ```dotenv
   SUPABASE_AUTH_ENABLED=true
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
   DATABASE_PATH=data/daily_mind.sqlite3
   CREDIT_SEARCH_CONFIRMED_FREE=false
   ```

   Replace the URL/key placeholders privately in your editor. No service-role key,
   secret API key, database password or signing secret is needed. The public key is
   intentionally returned to the browser; Exa/Tavily/model keys remain server-only.
   Only the modern publishable key format is supported. Restart FastAPI after edits.
5. Install and run from **your chosen checkout**, preserving any existing `.env`:

   ```powershell
   python -m pip install -e ".[dev]"
   python -m playwright install chromium
   cd frontend
   npm.cmd ci
   npm.cmd run build
   cd ..
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8002
   ```

   Open `http://127.0.0.1:8002`. If using Vite development mode, adjust its existing
   proxy from port 8000 to the backend port you chose. The built app needs no proxy.
   Avoid running the worktree against your main application's SQLite file until
   you have reviewed this branch. No existing database was copied or changed here.

Supabase's default email sender is restricted to project-team recipients and has
strict rate limits. See [email delivery restrictions](https://supabase.com/docs/guides/auth/auth-smtp).
For a no-spend demo, use an authorized test recipient; do not purchase email delivery
to make signup work. Free projects can pause after inactivity. Provider configuration,
email confirmation delivery and real signup require your own project; they cannot
be verified by synthetic browser tests.

## User behavior

- Sign up, confirm your email, sign in, then complete the existing interest onboarding
  for the new account. Sessions persist using the official Supabase browser SDK.
- Refreshing an expired session uses the SDK's refresh-token flow. A rejected API
  session locks the account view and offers sign-in or an explicit return to Guest Mode.
- Sign-out returns to the **same existing guest UUID**, clears local session storage,
  and attempts device-local refresh-session revocation. A network failure still clears
  this device locally and reports that remote revocation could not be confirmed.
- Accounts never claim, merge, reset or overwrite the current guest profile. Guest
  migration is intentionally deferred: a legacy guest UUID alone is insufficient
  evidence of ownership for a secure claim operation. Both profiles remain available.
- With authentication disabled/unconfigured, optional account screens explain the
  configuration requirement and the newspaper works in Guest Mode. Reader IDs already
  mapped to accounts remain protected even when authentication is later disabled.

## API and security

`GET /api/auth/config` returns `enabled`, `url`, `publishable_key`; missing/invalid
configuration returns disabled and empty fields. `GET /api/auth/me` requires a bearer
access token and returns its server-mapped `reader_id`.

All private newspaper APIs accept `Authorization: Bearer <access_token>`. FastAPI
verifies the signature via the configured project's HTTPS JWKS, exact issuer
`<SUPABASE_URL>/auth/v1`, audience `authenticated`, expiration, issuance/not-before,
UUID subject and authenticated role. Anonymous/service-role tokens are rejected.
Algorithms are restricted to ES256/RS256. Token-supplied key URLs are never followed.
Authenticated requests always resolve to the server's SQLite mapping, regardless of
any `X-Reader-ID`, `reader_id` or `profile_id` supplied by the caller. Edition/PDF/image/
story ownership checks use that resolved ID. Invalid bearer tokens never downgrade
silently to guest requests. API responses use `Cache-Control: no-store` and vary by
Authorization and X-Reader-ID, preventing browser cache reuse between accounts.

The additive table is `auth_readers(subject TEXT PRIMARY KEY, reader_id TEXT UNIQUE NOT NULL)`.
Reader allocation is transactional and persistent. Emails/passwords/refresh tokens
are not stored in SQLite. Existing tables, archives and immutable snapshots are retained.
Guest UUIDs retain their existing capability-based local-demo semantics; do not treat
an unclaimed guest profile as an authenticated account.

JWKS retrieval has a four-second total deadline, a five-minute cache, one concurrent
fetch and a ten-second minimum refresh interval to bound unknown-key storms. Existing
cached keys permit local verification during short provider outages; after cache expiry
verification fails closed with 503. Invalid/expired tokens return 401. SDK HTTP calls
have eight-second deadlines; UI session operations have twelve-second deadlines.
Supabase also caches discovery keys at its edge, so revocation is not instantaneous.
Offline JWT verification does not check session deletion/user bans on every request;
already-issued access tokens can remain valid until expiration. Use short provider
access-token lifetimes appropriate for the demo. No claim of instant global logout is made.

Browser session storage is subject to the same-origin/XSS threat model of an SPA.
Use HTTPS outside localhost. This optional hackathon feature does not add MFA, OAuth,
account deletion, password-reset screens, guest migration or a production auth audit.

## Repeatable local verification

```powershell
python -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
cd ..
python scripts/auth_browser_smoke.py
```

The auth tests use synthetic accounts, ephemeral real RSA/EC keys, mocked Supabase
HTTP and isolated SQLite. They send no email and need no secrets. The browser runner
starts/stops its own localhost server and writes ignored screenshots, JSON and the
matching PDF under `artifacts/`. See `AUTH_IMPLEMENTATION_REPORT.md` for actual results.
