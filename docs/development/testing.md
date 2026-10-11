# Testing and checks

`make check` is the single entry point: lint, formatting, types, templates, CSS, secrets in
staged changes, Django's deploy checks, and the test suite. It runs in the dev container so
results don't depend on the host. Run it before every commit.

Bandit, pip-audit and npm audit report but don't fail the run.

## Running part of the suite

While iterating, run one app, module, class or method:

```
make test-label TEST=tracker.tests.test_item_library
make test-label TEST=tracker.tests.test_item_library.SomeTestCase.test_something
```

`make test` runs the whole suite alone.

## Environment

Django's test runner creates a disposable test database on the Compose PostgreSQL and drops
it after the run; each test case runs in a transaction rolled back at its end. Nothing
outside the test database is shared.
