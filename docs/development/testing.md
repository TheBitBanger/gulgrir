# Testing and checks

Each verification item in a domain's `design.md` names its method: test, inspection,
demonstration or analysis. They run as follows:

| Kind              | What it is                                                                                     | When it runs |
| ----------------- | ---------------------------------------------------------------------------------------------- | ------------ |
| test: code test   | Automated test of logic we wrote, run by `make check`                                          | before every commit |
| demonstration: probe | A manual check, such as `curl` against the dev stack, that an invariant holds where it rests on a library or on wiring rather than on our logic | once, when the invariant is set up or its wiring changes |
| test: image smoke test | `make smoke-test-image`: builds the release image and starts it through `compose.yml`, as an install does, on a fresh database | before tagging, and in the publish workflow before pushing |
| demonstration: rehearsal | Restore a copy of the production backup into dev, run the release on it, and compare          | before tagging a release that changes data or routing |
| inspection        | A checklist read against the change                                                           | at the commit checkpoint |

## make check

`make check` is the only quality target ([0006](../system/decisions/0006-one-check-target-with-biome.md)):
lint, formatting, types, templates, CSS, secrets in staged changes, Django's deploy checks,
and both apps' test suites, always in full. It runs `scripts/check.sh` in the dev container
so results don't depend on the host, prints one line per check, and shows a check's output
only when it fails. Every check runs even after one fails.

Bandit, pip-audit and npm audit only warn; the warning names the command that lists their
findings.

## Environment

Django's test runner creates a disposable test database on the Compose PostgreSQL and drops
it after the run; each test case runs in a transaction rolled back at its end. The new app's
tests touch nothing outside the process. The image smoke test runs `compose.yml` from a
temporary directory under its own project name, so it never touches the dev stack, and
removes its containers, volume, image and directory afterwards. Nothing else is shared.
