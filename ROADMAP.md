# Full Rewrite & Migration Roadmap

This roadmap covers stabilization of the current Django app, then a parallel-stack migration to a new system. It includes the agreed tech stack, architecture, and the integration of time tracking (specification.md) mapped to UserItems (media/projects).

---

# A. Target Stack (for the rewrite)

## Backend
- NestJS (TypeScript)
- Reasons: strong structure for large domain, end-to-end typing, great queue tooling.

## Frontend
- SvelteKit
- Reasons: eye-candy friendly, great animations, small bundles.

## Data & Infra
- PostgreSQL (shared during migration)
- Redis (BullMQ queues)
- Optional: Meilisearch for fuzzy search (later)
- Reverse proxy: Caddy (or Nginx)

## Deployment
- Docker Compose
- GHCR image distribution for users

## Architecture Summary
- Services (bounded contexts):
  - media, projects, user_items, lists, ratings, revisits
  - time_tracking (specification.md mapped to UserItems)
  - reminders, random_picker
  - providers (TVDB/IMDB/etc)
  - imports/exports
- Data ownership model:
  - Shared DB during migration
  - Each table has a single writer (Django or new stack)

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
- [x] Document current behavior baseline (features/known issues)
- [x] Add user install path to README
- [x] Add release checklist
- [x] Align admin env vars with createsuperuser_if_none

Outputs/Artifacts:
- `docs/behavior-baseline.md`
- README install section (or `docs/install.md` if preferred)
- `docs/release-checklist.md`

Exit criteria:
- Baseline doc exists and is referenced from README
- Install path documented with commands that match compose files
- Release checklist is present and usable

Session checklist:
- [x] Create baseline doc outline and fill first pass
- [ ] Add install section with compose commands
- [ ] Add release checklist skeleton

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

Outputs/Artifacts:
- `compose.yml`
- `.env.example` (if needed)

Exit criteria:
- `docker compose up -d` starts app + db
- Data persists via volumes

Session checklist:
- [ ] Draft compose services
- [ ] Add volumes and env file
- [ ] Document usage in README

Notes/Decisions:
- (Capture env var defaults and volume paths)

## B4. Image Publishing (GitHub Actions)
Goal: automated GHCR build and push.

Inputs/Prereqs: production Dockerfile.

Notes/Decisions:
- Prereq: create GitHub repo + set remote; enable GHCR for the owner/org.
- Branch model: `main` is stable (batched releases), `dev` is fast channel; promote from `dev` to `main` when stable.
- Target image path: `ghcr.io/<org>/gulgrir`.
- Trigger: tag-only releases (`vX.Y.Z`) + manual dispatch (no push-on-commit).
- Tags: `latest` + version tag.
- Branch policy: `main` stable; optional `dev` for fast iteration; no separate nightly for now.

Tasks:
- [ ] Verify `gh` CLI installed and authenticated
- [ ] Create GitHub repo and set `origin` remote
- [ ] Create `dev` branch and push both `main` and `dev`
- [ ] Add GH Actions workflow
- [ ] Configure tags (latest + version/SHA)
- [ ] Optional: SBOM/provenance

Outputs/Artifacts:
- `.github/workflows/publish-image.yml`

Exit criteria:
- Workflow builds image
- Image is available in GHCR

Session checklist:
- [ ] Check `gh --version` and `gh auth status`
- [ ] Create repo via `gh repo create` (or manually)
- [ ] Add `origin` remote and push current branch
- [ ] Create/push `dev` branch
- [ ] Draft workflow
- [ ] Add tag logic
- [ ] Verify actions permissions

Notes/Decisions:
- (Capture tagging scheme and security options)

## B5. Deployment Notes
Goal: clear deploy steps for home server.

Inputs/Prereqs: compose.yml and image.

Tasks:
- [ ] Add home-server install steps
- [ ] Add DB migration + backup/restore steps

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
- [ ] Container boot
- [ ] DB connectivity
- [ ] Login/signup
- [ ] Basic page render

Outputs/Artifacts:
- `docs/smoke-tests.md`

Exit criteria:
- Checklist can be followed end-to-end

Session checklist:
- [ ] Write smoke checklist
- [ ] Include expected results per step

Notes/Decisions:
- (Capture any test environment requirements)

Exit criteria: users can run `docker compose up -d` using the published image and the app works.

---

# C. Parallel Stack Migration (Strangler-Fig)

Strategy: new stack runs in parallel; features migrate slice-by-slice. No “hand-wired” TS into Django.

## C1. New Stack Baseline
- Bootstrap NestJS + SvelteKit + Postgres + Redis
- Add auth (local users, isolated per user)
- Decide shared DB schema boundaries
- Set up reverse proxy routing (`/new/*` to new UI, `/` stays Django)

Exit: new stack runs alongside Django with its own empty schema.

## C2. Data Ownership Model
- Shared Postgres
- Rules:
  - Django owns legacy tables
  - New stack owns new tables
  - No dual writers

Exit: data model documented with table ownership matrix.

## C3. First Read-Only Slice (UI)
- Build a read-only UserItem list view in new UI
- Validate display parity vs Django
- Keep Django the source of truth for writes

Exit: new UI shows current data without writes.

---

# D. Early Implementation of specification.md (Time Tracking)

Map “Activities” to UserItems. This becomes the first new-stack-owned subsystem.

## D1. Time Tracking Core Tables (New Stack Ownership)
- active_timer (single active per user)
- time_entries (start/end/duration)
- profiles / groups / assignments

## D2. UI + API for Timer Core
- Start/stop timer
- Manual time entry
- Edit entry
- Single active timer enforcement
- Timezone awareness

## D3. Stats + Basic Visualization
- Time window selection
- Activity breakdown
- Group profile breakdown

Exit: time tracking works end-to-end in the new stack.

---

# E. Write-Path Migration (Media & Projects)

Migrate features from Django to the new stack, one slice at a time.

## E1. Ratings + Backlog
- Ratings CRUD
- Backlog state
- Revisit tracking

## E2. Random Picker
- Weighted selection
- Filters by type, status, etc.

## E3. Reminders
- Revisit reminders
- Notification scheduling

Exit: key write paths moved off Django.

---

# F. Providers + Import/Export

## F1. Providers
- Scheduled sync (daily)
- Rate limiting + backoff
- Provider adapters per media type

## F2. Import/Export
- Import lists from providers
- Export data (JSON/CSV)
- Background jobs for large exports

Exit: provider integration stable.

---

# G. Testing Strategy

## G1. Step-0
- Container smoke tests

## G2. API Tests
- Core endpoints for UserItems + TimeTracking

## G3. Integration Tests
- Timer invariants (single active timer)
- Stats consistency after edits

## G4. Provider Tests
- Mocked provider responses
- Rate limiting behavior

---

# H. Full Cutover

- Switch main routing to new app
- Django read-only fallback
- Data verification
- Retire Django once stable

---

# Notes for Next Session
- Stack: NestJS + SvelteKit + Postgres + Redis + BullMQ
- Time tracking spec maps to UserItems (media/projects)
- Incremental migration with shared DB and strict ownership
- Step-0 stabilization is required before rewrite work
- Step-0 progress: B1/B2/B3 done; B4 pending GH repo + GHCR setup
