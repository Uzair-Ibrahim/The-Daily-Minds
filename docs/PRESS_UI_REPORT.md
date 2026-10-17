# Reference-inspired newspaper UI

Implemented on main using the user's newspaper reference. No Lovable framework,
service or generated template was introduced. The unused local branch is preserved.

The UI now has warm cream paper, a locally hosted blackletter masthead, ruled
section navigation, bold serif headlines, maroon actions with ink shadows, and a
split lead headline/photo layout on desktop. Mobile stacks the lead story. The
existing image attribution and unavailable-image states remain. Onboarding,
archives, Interest DNA and account dialogs use the same palette. PDF rendering
retains its existing dedicated print layout and saved-edition content.

Changed source files:

- `frontend/src/main.jsx`: masthead structure and headline spacing.
- `frontend/src/press.css`: reference-inspired responsive visual theme.
- `frontend/index.html`: matching browser theme and local font preload.
- `frontend/public/fonts/UnifrakturMaguntia-Book.ttf` and `OFL.txt`: unmodified
  open font with complete SIL license.
- `docs/ATTRIBUTIONS.md`: font provenance.
- `scripts/browser_smoke.py`: normalize a PDF hyphen split at a line break and
  compare archive titles using DOM text, which preserves case under uppercase CSS.

Actual verification on 17 October 2026:

- Backend: **222 passed, 4 skipped**, 106.97 seconds. Optional provider/Postgres
  integration tests were not enabled for this UI-only change.
- Frontend: **4 passed**; final Vite production build passed in 10.47 seconds.
- Real public RSS browser journey: **PASS**, eight articles; onboarding,
  likes/saves/skips, feedback score changes, versioned archives, reload,
  preference editing/cancellation and reset. No uncaught browser errors.
- PDF: **four pages**, matching saved edition ID/date and every headline.
- Layout: **1440, 1024, 768, 390 and 320px** passed without horizontal overflow.
- Bundled font loaded in Chromium; sign-in/signup dialogs opened/closed on mobile.
  No real signup email was sent by these checks.

Local evidence is ignored under `artifacts/`: `press-regression.txt`,
`browser-smoke.json`, `press-visual-checks.json`, `press-final-desktop.png`,
`press-final-mobile.png`, `press-signin-mobile.png`, and `daily-mind-live.pdf`.
QA used a separate disposable SQLite file; existing local data was preserved.

Earlier attempts on the existing local development server timed out gathering
news. Verification passed on an isolated server with semantic embeddings disabled,
matching the current lightweight Render configuration. Initial browser assertions
also exposed PDF line-break and CSS uppercase comparison assumptions; the harness
was corrected without changing publisher content or PDF generation.

News/photo availability still depends on publishers. No stock or generated news
photographs were added. The reference's portrait and portfolio text were not used.
