# 0006. One check target, with Biome for the TypeScript app

- Status: accepted
- Date: 2026-10-11

## Context

[0002](0002-typescript-full-stack.md) adds a TypeScript app beside Django. The Python side
already had `make check` for lint, format, types and audits, and `make test` for the test
suite alone. The TypeScript app needs a linter and a formatter, and it is on TypeScript 7,
the native rewrite of the compiler.

Code quality is one question: does this change pass lint, format, types and tests? With
both suites taking seconds and the whole run about 15 seconds, splitting it buys nothing,
and a full run printed hundreds of lines, mostly audit findings that never fail it.

## Alternatives

| Option                                      | Rejected because                                                                                   |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Keep `make test` beside `make check`        | Two answers to one question; a passing `make test` says nothing about lint or types.               |
| Run part of a suite (`make test-label`)     | The suites run in seconds, so a partial run only hides failures.                                   |
| ESLint with typescript-eslint, and Prettier | Two tools and several packages; typescript-eslint builds on the compiler's JavaScript API, which TypeScript 7 changes. |

## Decision

`make check` is the only quality target. It runs every check in the dev container, in
full, and prints one line per check; a check's own output appears only when it fails.
Audits that report known findings (bandit, pip-audit, npm audit) print a one-line warning
and never fail the run.

Biome lints and formats the TypeScript app, with warnings treated as errors. `tsc` checks
its types.

## Consequences

- One command to run before every commit, short enough to run often.
- Biome has fewer type-aware lint rules than typescript-eslint; strict `tsc` covers most of
  the gap.
- Audit findings stay out of sight until someone runs the audit; the warning line names the
  command.
