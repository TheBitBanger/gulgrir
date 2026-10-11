# Code style

Ruff and the other checks in `make check` enforce formatting and imports. Beyond what they
catch:

- Scope every lookup of user data to the requesting user (`get_object_or_404` with the
  user in the filter), so one account never reaches another's rows.
- Wrap multi-step writes in `transaction.atomic()`, and catch `IntegrityError` where a
  unique constraint can race.
- Logging is `print(..., file=sys.stderr, flush=True)`; there is no logging setup.
