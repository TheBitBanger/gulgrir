# Release Checklist

Use this checklist for each release. Keep it short and executable.

## Pre-release
- [ ] Confirm scope and version identifier
- [ ] Review open issues that block release
- [ ] Run non-regression checks (manual; expand this list as new features ship or regressions are found)

## Build and Publish (GHCR)
- [ ] Build production image
- [ ] Stable tag: `vX.Y` on `master` (publishes `latest` + `vX.Y`)
- [ ] Dev tag: `vX.Y.Z` on `dev` (publishes `dev` + `vX.Y.Z`)
- [ ] Push tag to GitHub to trigger the workflow

## Deployment Prep
- [ ] Confirm `compose.yml` and `.env` examples are up to date
- [ ] Verify migration/restore steps match current docs

## Owner QA (manual)
- [ ] Owner runs smoke tests
- [ ] Owner performs UX/UI validation

## Release Complete
- [ ] Update release notes
- [ ] Announce or document the release location
