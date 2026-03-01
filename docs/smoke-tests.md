# Smoke Tests

Quick checks to validate a deployment without full regression testing.

## Preconditions
- Stack is running (`docker compose up -d`)
- You know the base URL (local: `http://localhost:8765`)

## Automated (CLI)
- [ ] Admin login page returns 200
  - Command: `curl -fsS http://localhost:8765/admin/login/`
- [ ] Admin root redirects to login and returns 200
  - Command: `curl -fsS -L http://localhost:8765/admin/`
- [ ] Admin static CSS returns 200
  - Command: `curl -fsS http://localhost:8765/static/admin/css/base.css`
- [ ] Admin static JS returns 200
  - Command: `curl -fsS http://localhost:8765/static/admin/js/nav_sidebar.js`

## Manual (UI)
- [ ] Load `/admin/` and verify styles load
- [ ] Log in with admin user
- [ ] Confirm dashboard renders without errors

## Expected Results
- CLI checks exit with status 0
- Browser shows styled admin login
- No CSRF trusted origin errors
