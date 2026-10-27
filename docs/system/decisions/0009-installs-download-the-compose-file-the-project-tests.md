# 0009. Installs download the compose file the project runs and tests

- Status: accepted
- Date: 2026-10-26

## Context

Installs copied a compose file out of the install guide, while development ran a different
one in `compose/`. The two drifted: the guide's copy kept the deprecated `entrypoint` and
`command` lines and ran the backup service as root. The smoke test started the image with
`docker run`, so neither file was checked against a release (SYS-12). Every local change
went into the copy, so a release that changed the file meant a hand merge (SYS-13).

## Alternatives

| Option                                                    | Rejected because                                                                   |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Keep the copy in the guide and test that copy             | Extracting YAML from Markdown to test it keeps two copies and a fragile extractor.  |
| Ship the compose file inside the image                    | Installs need it before the image runs, and may add their own services (0005, 0007). |
| Ship the backup service, in `compose.yml` behind a profile or in a file of its own | It is a third-party service the project neither builds nor tests, and backups are meant to move into the app. |
| Hardcode `:latest` and pin by editing `compose.yml` or an override | Replacing `compose.yml` on upgrade drops an edit, and an override is YAML for a one-word choice. |

## Decision

The repository root holds `compose.yml`, the required stack of app and database, running
the image tag `GULGRIR_VERSION` names, `latest` by default. Installs download it from the
release's ref and never edit it. A default install sets only the required secrets in `.env`;
pinning a release or changing the port is one more line there. Anything a setting cannot
express, such as the optional backup service, goes in the install's own
`compose.override.yml`, which Compose loads on its own. The backups guide gives the
backup service as an override. The smoke test runs `compose.yml` in an empty directory, as
an install does. The dev stack runs it with `compose.dev.yml` on top and has no backup
service.

## Consequences

- Every install that copied the guide's file switches once, following
  [install](../../operations/install.md).
- Upgrading replaces `compose.yml`, never merges it. A release whose compose change needs
  more than that is a breaking change and adds an upgrade step to the guide.
- Until the first promotion `:latest` does not exist, so `GULGRIR_VERSION` defaults to
  `dev`; the promotion switches the default.
- `GULGRIR_VERSION` joins the configuration check's list, like `GULGRIR_PORT`, since the
  app receives `.env` and the check flags unknown `GULGRIR_*` names.
- The backup override in the guide is untested; a backup run is checked by hand when the
  install switches.
- `compose/` goes away. Compose now finds `.env` beside `compose.yml`, so 0007's note about
  the dev stack passing `--env-file` no longer applies.
