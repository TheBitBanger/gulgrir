# Configuration design

Contracts and Verification bind; Structure describes the code as built. The settings, their
defaults, their old names and how their values are read are listed in
[configuration](../../operations/configuration.md); that list is part of the contracts.

## Contracts

| Serves        | Contract |
| ------------- | -------- |
| SYS-4, CFG-1  | Every setting is an environment variable named `GULGRIR_*`, set in `.env` only to override its default. The app receives the whole `.env`. The database and backup services receive the database settings through the compose file, under the `POSTGRES_*` names they read, from the new name, else the old one, else the default; the backup service also receives `.env` for its own settings. The compose file changes only when a service, or a setting a service reads, is added, renamed or removed ([0007](../decisions/0007-compose-maps-database-settings.md)). |
| SYS-11        | A renamed setting still works under its old name, which is reported as deprecated. When both names are set, the new one wins. An empty value counts as unset. |
| SYS-11        | Django reads each setting it uses from its `GULGRIR_*` name, else from its old name, else from its default ([0008](../decisions/0008-django-reads-the-new-setting-names.md)). Django gains no new settings; a setting added from now on belongs to the new app. A Django command run by hand in the container therefore sees the same values as start-up. |
| SYS-11        | At start-up the check hands Django every setting under its `GULGRIR_*` name, resolved as above. `GULGRIR_DEBUG` and `GULGRIR_BEHIND_HTTPS_PROXY` are passed as `true` or `false`, and `GULGRIR_ENV` as `production`, `staging` or `dev`, matching the report's reading. Every other value is passed exactly as written. |
| SYS-4         | Secrets and `GULGRIR_ADMIN_USER` have no default; every other setting has one. `GULGRIR_SECRET_KEY` and `GULGRIR_DB_PASSWORD` are required. `GULGRIR_ADMIN_USER` and `GULGRIR_ADMIN_PASSWORD` are needed only to create the first superuser (ACC-S1). |
| CFG-1         | Before either app starts, the log shows one line per setting with columns `SETTING`, `DEFAULT`, `OVERRIDE`, `IN EFFECT` and `NOTE`. When a setting with fixed meanings is written in a form the list doesn't name, `NOTE` says how it was read; start-up continues. |
| CFG-1         | The report says what to change. A setting given under its old name only is noted as deprecated, with the new name to rename it to. A setting given under both names is noted with the old name as ignored and to be deleted. An unknown `GULGRIR_*` variable is flagged, naming the closest known setting when one is a letter or two away. An unknown variable's value is never shown. |
| CFG-1         | Start-up stops when a required secret is missing or `GULGRIR_DB_PORT` is not a whole number from 1 to 65535. The report still prints, and its last line names each variable at fault and why. For a missing secret it gives a command that generates one using only `A-Z a-z 0-9 - _`. |
| CFG-1         | No secret's value appears in any log. In the report a secret's `DEFAULT` is `(none)`, its `OVERRIDE` is `(set)` or `(missing)`, and its `IN EFFECT` is `(redacted)`. |

## Structure

The configuration check is one pure function, `checkConfig(env)` in `app/src/config.ts`. It
takes the process environment and returns whether start-up may continue, the report lines,
and the environment to hand Django. It reads no files and writes no log, so the caller
decides where the report goes and whether to stop.

### One table drives everything

Each setting is one entry in a list: its name, old name, default, whether it is a secret or
required, and how its value is read (`text`, `flag`, `env`, `port`). The report rows, the
deprecation notes, the redaction and the values handed to Django all come from that entry,
so adding a setting is one line. The list mirrors the settings table in
[configuration](../../operations/configuration.md).

### Handing settings to Django

The check hands each value over under its new name, already resolved, and Django falls back
to the old name only when the new one is unset, which happens only outside start-up. Flags
and `GULGRIR_ENV` are handed over already read, so Django's own parsing in
`src/gulgrir/settings.py` reaches the same result and the report cannot disagree with it.
The readings copy that file's: a flag is true only for `true` in any case, and
`GULGRIR_ENV` uses the aliases of `normalize_environment`. Django's fallback is a second
copy of the old names and defaults, accepted in
[0008](../decisions/0008-django-reads-the-new-setting-names.md).

### Other services

The check runs in the app container and cannot reach the database or backup containers.
The compose file maps their settings instead, with the same fallback order and defaults
([0007](../decisions/0007-compose-maps-database-settings.md)).

### Reading a value

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

## Verification

| ID     | Serves               | Method        | Check |
| ------ | -------------------- | ------------- | ----- |
| CFG-V1 | SYS-4, CFG-1         | inspection    | `compose.yml` and the backup override in [backups](../../operations/backups.md) give the app `.env`, give the database service no `.env`, and map each `GULGRIR_DB_*` setting to its `POSTGRES_*` name with the old name, then the default, as fallback. |
| CFG-V2 | SYS-4                | demonstration | With an `.env` holding only `GULGRIR_DB_PASSWORD`, then only `POSTGRES_PASSWORD`, `docker compose config` shows that value as the database service's `POSTGRES_PASSWORD`, and the stack starts. |
| CFG-V3 | SYS-11, CFG-1        | test          | `config.test.ts`, "renamed settings (CFG-V3)" and "unknown variables (CFG-V3)" |
| CFG-V4 | SYS-11               | test          | `config.test.ts`, "values handed to Django (CFG-V4)" |
| CFG-V5 | SYS-11               | inspection    | `src/gulgrir/settings.py` and `createsuperuser_if_none` read every setting through one helper that tries the new name, then the old one, then the default, and read no setting the list doesn't name. |
| CFG-V6 | SYS-11               | test          | `test_superuser_bootstrap.py`, `test_reads_new_names_before_old_ones` (CFG-V6) |
| CFG-V7 | SYS-4                | test          | `config.test.ts`, "defaults (CFG-V7)" |
| CFG-V8 | CFG-1                | test          | `config.test.ts`, "report layout (CFG-V8)" |
| CFG-V9 | CFG-1                | test          | `config.test.ts`, "what stops start-up (CFG-V9)" |
| CFG-V10 | CFG-1               | test          | `config.test.ts`, "secrets (CFG-V10)" |
| CFG-V11 | CFG-1               | inspection    | No code that writes to a log prints a setting's value without going through the report's redaction. |
| CFG-V12 | CFG-1               | inspection    | Each note in `config.ts` tells the administrator what to do: a deprecated name says to rename it to the new name, an old name set beside the new one says to delete it. |
