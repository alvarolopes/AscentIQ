# AscentIQ Private Dashboard

A local React dashboard and reproducible Typst HTML/PDF reports. All calculations
run in Python using the existing athlete database. No LLM or hosted Typst account
is required to view, synchronize, or generate a report.

The interface is dark-only with a GitHub-inspired palette, compact top navigation,
and a centered, boxed layout capped at 1200 px. Native Typst HTML reports share
the dark styling; PDFs remain light for printing and include training data only.

## Open The Dashboard

Open http://localhost:8787. The default username is `athlete`; the generated password is in
`runtime/dashboard/access.txt`. This file is private, ignored by Git, and must not
be shared or committed. Authentication is separate from Garmin and Hevy.

From the athlete-agent directory:

```powershell
docker compose up -d --build
docker compose ps
```

Docker Desktop must be running. Stop only this application's services with
`docker compose stop`; other Docker applications are not affected.

Before the first start, copy `.env.example` to a private `.env` and fill the
provider credentials locally. Create `data`, `analysis`,
`activities/notes/medical`, and `runtime/dashboard` as local directories.
Supply your own athlete JSON files; no real athlete database, generated report,
medical result, screenshot, or credential is shipped with this implementation.
Missing records are displayed as unavailable, not as example personal results.

## Views And Reports

- Overview: Fitness, Fatigue, Form, daily load, recent activities and source dates.
- Running: date/search filters, weekly distance, D+, heart rate and historical race index.
- Strength: consolidated Garmin/Hevy sessions, exercises, sets, reps, loads and RPE.
- Body: dated weight, body-fat percentage, lean mass, perimetry and skinfolds.
- Medical: stored results, original private documents and existing medical context.
- Reports: job status, previous PDFs, manual generation and synchronization.

The header provides **Dashboard Typst HTML** and **Baixar PDF**. The Typst HTML
page also includes its own PDF button. Both exports derive from the same immutable
snapshot. The PDF receives a separate allowlisted training-only input: running,
strength and training load, without body measurements, medical exams, physiology
tests or nutrition targets. Older full PDFs remain in the private archive on disk
but are not listed or downloadable through the dashboard. React supplies interactive filters and charts; the Typst export is a
static, dated report. Typst 0.15.1 HTML export is experimental and explicitly enabled;
it is not a self-hosted copy of the proprietary typst.app editor.

`Gerar com a base atual` publishes reports without contacting remote providers.
`Atualizar treinos e gerar` synchronizes Garmin and Hevy, consolidates sessions,
rebuilds the existing models and publishes new HTML/PDF outputs. Garmin uses a
seven-day overlap and skips activities already present. Hevy uses the existing
incremental importer. Provider failures are shown as partial updates, never as a
successful complete synchronization.

## Weekly Job

The internal scheduler runs on Mondays at 07:00 in `America/Sao_Paulo`, while
Docker is running. It persists its scheduling state and catches up one missed
weekly run after a subsequent restart. The first start generates from the local
base instead of silently downloading an entire remote history. Set
`DASHBOARD_SCHEDULE_ENABLED=false` in Compose to disable scheduling.

Only one update can run at a time. Job state is persisted in SQLite. A failed
render does not replace the previous successful report: HTML and PDF must both
validate before the latest-report pointer is atomically replaced.

## Data Semantics

The existing load model is preserved: chronic load over 42 days, acute load over
7 days, and Form = Fitness - Fatigue. It is not official TrainingPeaks TSS, a
fitness percentage, VO2max, or a medical assessment. Garmin/Strava activity
records drive the load series, with muscular details from linked Hevy sessions.
Hevy-only sessions appear in the strength diary but are not automatically added
to the load model. This can make diary counts differ from cardiovascular counts.

Missing values remain unknown. Measurement and medical dates are shown instead
of extrapolating them to today. Medical conclusions and nutrition targets are
previously recorded references, not new diagnoses or prescriptions. The race
index is a dated historical benchmark, not current readiness.

## Privacy And Credentials

The web port binds only to `127.0.0.1`. The API has no host port. Private routes
require a session; cookies are HttpOnly/SameSite, state-changing requests have
origin checks, and login attempts are rate limited. No public hosting, analytics,
external fonts or browser access to provider credentials is configured.

Existing provider credentials are loaded from the project `.env`; do not put
them in source code. Garmin auth tokens are persisted in the `garmin_auth` Docker
volume. An account requiring MFA may need a separate authentication step; errors
remain visible in the update job without publishing credentials.

The PWA manifest is included, but its service worker does not cache health data,
API responses or authenticated pages. Phone access requires an additional private
HTTPS deployment; this localhost setup does not expose your medical data to the LAN.

Keep `data`, `analysis`, medical source files, `.env`, `runtime/dashboard`, and the
Garmin auth volume in a private backup. Never copy these into the public portfolio.
The app cannot read arbitrary files: medical downloads use a whitelist rooted in
`activities/notes/medical`, and report identifiers are validated.

## Implementation And Verification

`snapshot.py` normalizes and sanitizes the existing JSON files. `pipeline.py`
reuses the deterministic importers and publishes both Typst formats. `jobs.py`
owns the scheduler, persisted queue and process lock. `server.py` supplies the
authenticated API. `web` contains the React interface and `templates` the Typst
reports. Python, Typst and direct frontend dependencies use fixed versions.

```powershell
docker compose run --rm --no-deps api python -m unittest discover -s dashboard/tests -v
```

To inspect container status or logs:

```powershell
docker compose ps
docker compose logs --tail 80 api web
```

Do not publish raw connector logs. Run a single API worker: scheduling and
background execution are designed for this single-user local deployment.
