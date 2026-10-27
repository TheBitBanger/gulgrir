# Releasing

Releases are numbered `r1`, `r2`, … with no padding; version sort (`git tag
--sort=v:refname`) orders them. Each release ships through two channels of
`ghcr.io/thebitbanger/gulgrir`:

| Channel   | Gets a release                                   | Image tags            |
| --------- | ------------------------------------------------ | --------------------- |
| `dev`     | when `rN` is tagged on `dev`                     | `:dev`, `:rN`         |
| `latest`  | when `rN` is promoted after days of daily use    | `:latest`             |

Promotion re-points `:latest` at the image `rN` already published, without rebuilding, so
stable is exactly what ran on `dev`. It also fast-forwards `master` to `rN`, so
`git describe --tags origin/master` names the release `:latest` serves.

## Cutting a release

1. Run `make check` and `make smoke-test-image`, exercise the change in development, and
   rehearse on a copy of the production backup
   ([restoring it into dev](environment.md#restore-a-production-backup)) if the release
   changes data or routing.
2. Tag and push: `git tag rN && git push origin rN`. The publish workflow refuses a tag
   that isn't `rN` or isn't on `dev`.
3. Pull `:dev` on the server and use it.
4. Check where `:latest` is (`git describe --tags origin/master`). If an earlier release
   has had a few days of daily use without problems, promote it:
   `gh workflow run promote-image.yml -f tag=rN`.

Problems are fixed forward in a new release, never by rolling a channel back.

Until the first promotion `:latest` doesn't exist, so `GULGRIR_VERSION` defaults to `dev`,
in `compose.yml` and the configuration check, and the install guide downloads `compose.yml`
from `dev`. Right after the first promotion, switch the default to `latest` and the guide to
`master`.

Tags before `r1` (`v0.1.0` to `v0.3.0`) used an earlier scheme and stay as published.
