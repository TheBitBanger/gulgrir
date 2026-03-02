# Django-First Roadmap

This roadmap covers stabilization of the current Django app, then a focused build-out of core features in Django. The guiding principle is developer joy and simplicity: ship a working, maintainable product first, and only consider a different stack if forced by real constraints.

---

# A. Target Stack (Django-First)

## Backend
- Django 5.2 (Python 3.11+)
- Reasons: fastest path to a correct, maintainable CRUD app with auth, admin, and migrations included.

## Frontend
- Django templates + HTMX + small JS modules
- Reasons: modern UX without SPA complexity; fast iteration.

## Data & Infra
- PostgreSQL
- Optional: lightweight job runner (Django Q or similar)
- Optional: Redis only if/when queues outgrow simple scheduling

## Deployment
- Docker Compose
- GHCR image distribution for users

## Architecture Summary
- Single Django monolith with clear internal modules
- Services layer for core domain logic
- Provider adapters isolated behind interfaces
- Keep exit ramps open, but do not plan a rewrite

---

# Planning phase
Before starting any step below, do a short planning pass to flesh out tasks, artifacts, and exit criteria for that step, and capture decisions in “Notes/Decisions”.
Tracking: use roadmap checkboxes as the source of truth across sessions (`- [ ]` pending, `- [x]` done).

# B. Step-0: Stabilize Current Django App (Pre-Rewrite)

Goal: make the current app deployable, reproducible, and publishable as a container image.

## Deliverables
- Clean git history baseline
- Production Docker image (no dev server)
- Single user-facing `compose.yml`
- GHCR build pipeline
- Deployment guide
- Minimal smoke tests

## B1. Repo & Release Hygiene
Goal: baseline docs and release cadence clarity.

Inputs/Prereqs: current behavior and known limitations.

Tasks:
- [x] Add user install path to README
- [x] Add release checklist
- [x] Align admin env vars with createsuperuser_if_none

Outputs/Artifacts:
- README install section (or `docs/install.md` if preferred)
- `docs/release-checklist.md`

Exit criteria:
- Install path documented with commands that match compose files
- Release checklist is present and usable

Session checklist:
- [x] Add install section with compose commands
- [x] Add release checklist skeleton

Notes/Decisions:
- (Capture choices about doc location, structure, or scope)

## B2. Production Docker Image
Goal: build a production-ready image that runs without dev server.

Inputs/Prereqs: compose files, settings, static pipeline.

Tasks:
- [x] Create production Dockerfile
- [x] Replace dev server with production server
- [x] Ensure static assets build (Tailwind + HTMX)
- [x] Verify image runs without manual steps

Outputs/Artifacts:
- `Dockerfile` (production)
- `docs/build-notes.md` (optional)

Exit criteria:
- `docker build` succeeds
- Container serves app via production server
- Static assets present in container

Session checklist:
- [ ] Draft Dockerfile
- [ ] Update entrypoint/command to prod server
- [ ] Run container smoke check (if allowed later)

Notes/Decisions:
- (Capture server choice and asset build strategy)

## B3. User-Facing Compose File
Goal: single compose file for users.

Inputs/Prereqs: production image and env vars.

Tasks:
- [x] Create `compose.yml` for users (README snippet; update image URL after publish)
- [x] Add db + app services
- [x] Add volumes for data
- [x] Add `.env` support
- [x] Revisit dev compose setup; consolidate layered files into a single dev compose with bind mounts

Outputs/Artifacts:
- `compose.yml`
- `.env.example` (if needed)

Exit criteria:
- `docker compose up -d` starts app + db
- Data persists via volumes

Session checklist:
- [x] Draft compose services
- [x] Add volumes and env file
- [x] Document usage in README

Notes/Decisions:
- (Capture env var defaults and volume paths)

## B4. Image Publishing (GitHub Actions)
Goal: automated GHCR build and push.

Inputs/Prereqs: production Dockerfile.

Notes/Decisions:
- Prereq: create GitHub repo + set remote; enable GHCR for the owner/org.
- Branch model: `master` is stable (batched releases), `dev` is fast channel; promote from `dev` to `master` when stable.
- Target image path: `ghcr.io/<org>/gulgrir`.
- Trigger: tag-only releases (stable `vX.Y`, dev `vX.Y.Z`) + manual dispatch (no push-on-commit).
- Tags: stable publishes `latest` + `vX.Y`; dev publishes `dev` + `vX.Y.Z`.
- Branch policy: `master` stable; `dev` for fast iteration; no separate nightly for now.

Tasks:
- [x] Verify `gh` CLI installed and authenticated
- [x] Create GitHub repo and set `origin` remote
- [x] Create `dev` branch and push both `master` and `dev`
- [x] Add GH Actions workflow
- [x] Configure tags (stable `vX.Y`, dev `vX.Y.Z`)
- [x] Optional: SBOM/provenance

Outputs/Artifacts:
- `.github/workflows/publish-image.yml`

Exit criteria:
- Workflow builds image
- Image is available in GHCR

Session checklist:
- [x] Check `gh --version` and `gh auth status`
- [x] Create repo via `gh repo create` (or manually)
- [x] Add `origin` remote and push current branch
- [x] Create/push `dev` branch
- [x] Draft workflow
- [x] Add tag logic
- [x] Verify actions permissions

Notes/Decisions:
- (Capture tagging scheme and security options)

## B5. Deployment Notes
Goal: clear deploy steps for home server.

Inputs/Prereqs: compose.yml and image.

Tasks:
- [x] Add home-server install steps
- [x] Add DB migration + backup/restore steps

Outputs/Artifacts:
- `docs/deploy.md`

Exit criteria:
- Steps are complete and match actual commands

Session checklist:
- [ ] Draft deploy doc
- [ ] Link from README

Notes/Decisions:
- (Capture any host-specific assumptions)

## B6. Minimal Smoke Tests
Goal: quick validation steps post-deploy.

Inputs/Prereqs: running container.

Tasks:
- [x] Container boot
- [x] DB connectivity
- [x] Login/signup
- [x] Basic page render

Outputs/Artifacts:
- `docs/smoke-tests.md`

Exit criteria:
- Checklist can be followed end-to-end

Session checklist:
- [x] Write smoke checklist
- [x] Include expected results per step

Notes/Decisions:
- (Capture any test environment requirements)

Exit criteria: users can run `docker compose up -d` using the published image and the app works.

---

# C. Core Feature Build (Django)

Focus: deliver the time tracking feature and provider integrations inside the existing Django app, with simple UX and minimal infrastructure.

## C1. Time Tracking Core
- Active timer (single active per user)
- Time entries (start/end/duration)
- Profiles / groups / assignments

## C2. Timer UI + Sync
- Start/pause/stop timer
- Manual time entry
- Edit entry
- Client-side timer with periodic sync
- Enforce single active timer per user
- Timezone-aware display

## C3. Stats + Simple Visualization
- Time window selection
- Activity breakdown
- Group profile breakdown
- Simple charts/lists for trends and distribution

## C4. Providers + Imports
- Scheduled provider fetch
- Provider adapters per media type
- Import lists from providers on demand
- Rate limiting + backoff

Exit: time tracking and provider sync/import work end-to-end in Django.

---

# D. Stable Release (Post Time Tracking)

Goal: publish the first stable image once time tracking is polished.

Tasks:
- [ ] Cut stable tag `vX.Y` on `master`
- [ ] Publish `latest` + `vX.Y` image tags
- [ ] Update README to reference stable image/tag
- [ ] Run smoke tests against the stable image

Exit criteria: stable image is published and documented for end users.

---

# E. Testing Strategy

## E1. Step-0
- Container smoke tests

## E2. Core Feature Tests
- Timer invariants (single active timer)
- Stats consistency after edits

## E3. Provider Tests
- Mocked provider responses
- Rate limiting behavior

---

# Notes for Next Session
- Stack: Django + Postgres + HTMX + minimal JS
- Focus: ship time tracking and provider sync/import in Django
- Keep infrastructure minimal; add queues only if needed
- Step-0 progress: B1/B2/B3/B4/B5/B6 done; stable release deferred to D
