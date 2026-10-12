# Configuration architecture

The configuration check is one pure function, `checkConfig(env)` in `app/src/config.ts`. It
takes the process environment and returns whether start-up may continue, the report lines,
and the environment to hand Django. It reads no files and writes no log, so the caller
decides where the report goes and whether to stop.

## One table drives everything

Each setting is one entry in a list: its name, old name, default, whether it is a secret or
required, and how its value is read (`text`, `flag`, `env`, `port`). The report rows, the
deprecation notes, the redaction and the values handed to Django all come from that entry,
so adding a setting is one line. The list mirrors the settings table in
[configuration](../../operations/configuration.md), which is the specification.

## Handing settings to Django

Django still reads the old names (`DJANGO_*`, `POSTGRES_*`), so the check hands each value
over under its old name, or under its own name when it has none (`GULGRIR_ENV`). Flags and
`GULGRIR_ENV` are handed over already read, so Django's own parsing in
`src/gulgrir/settings.py` reaches the same result and the report cannot disagree with it.
The readings copy that file's: a flag is true only for `true` in any case, and
`GULGRIR_ENV` uses the aliases of `normalize_environment`.

## Other services

The check runs in the app container and cannot reach the database or backup containers.
The compose file maps their settings instead, with the same fallback order and defaults
([0007](../decisions/0007-compose-maps-database-settings.md)).

## Reading a value

| Step           | Rule                                                                                      |
| -------------- | ----------------------------------------------------------------------------------------- |
| Pick the value | New name, else old name, else default; an empty value counts as unset.                    |
| Read it        | By kind; a written form the list doesn't name is read anyway and noted.                   |
| Check it       | A missing required secret or an invalid port is a fault; faults stop start-up.            |
| Report it      | Secrets show only `(set)` or `(missing)` and `(redacted)`, never a value.                 |

Unknown `GULGRIR_*` variables are listed by name only, with the closest setting within an
edit distance of two. Faults go on the report's last line, so a log tail shows them.

The first superuser is not the check's concern: `createsuperuser_if_none` refuses to start
when none exists and its credentials are missing (ACC-S1), because only Django knows
whether a superuser exists.
