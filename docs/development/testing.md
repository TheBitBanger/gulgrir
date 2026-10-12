# Testing and checks

Each specification item names how it is verified. There are three kinds:

| Kind              | What it is                                                                                     | When it runs |
| ----------------- | ---------------------------------------------------------------------------------------------- | ------------ |
| code test         | Automated test of logic we wrote, run by `make check`                                          | before every commit |
| probe             | A manual check, such as `curl` against the dev stack, that an invariant holds where it rests on a library or on wiring rather than on our logic | once, when the invariant is set up or its wiring changes |
| review            | A rule checked by reading the change                                                           | at the commit checkpoint |

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
tests touch nothing outside the process. Nothing else is shared.
