# Configuration specification

Serves SYS-4, SYS-11 and CFG-1. The settings, their defaults, their old names and how their
values are read are listed in [configuration](../../operations/configuration.md); that list
is part of this specification. Kinds of verification are described in
[testing](../../development/testing.md).

| ID     | Behavior                                                                                                                                 | Verified by |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| CFG-S1 | Every setting is an environment variable named `GULGRIR_*`, set in `.env` only to override its default. The app receives the whole `.env`. The database and backup services receive the database settings through the compose file, under the `POSTGRES_*` names they read, from the new name, else the old one, else the default; the backup service also receives `.env` for its own settings. The compose file changes only when a service, or a setting a service reads, is added, renamed or removed ([0007](../decisions/0007-compose-maps-database-settings.md)). | review; probe for the mapping |
| CFG-S2 | A renamed setting still works under its old name, which is reported as deprecated. When both names are set, the new one wins.          | code test |
| CFG-S3 | Each app receives each setting under the name that app reads. `GULGRIR_DEBUG` and `GULGRIR_BEHIND_HTTPS_PROXY` are passed as `true` or `false`, and `GULGRIR_ENV` as `production`, `staging` or `dev`, matching the report's reading. Every other value is passed exactly as written. | code test |
| CFG-S4 | Secrets and `GULGRIR_ADMIN_USER` have no default; every other setting has one. `GULGRIR_SECRET_KEY` and `GULGRIR_DB_PASSWORD` are required. `GULGRIR_ADMIN_USER` and `GULGRIR_ADMIN_PASSWORD` are needed only to create the first superuser (ACC-S1). An empty value counts as missing. | code test |
| CFG-S5 | Before either app starts, the log shows one line per setting with columns `SETTING`, `DEFAULT`, `OVERRIDE`, `IN EFFECT` and `NOTE`. When a setting with fixed meanings is written in a form the list doesn't name, `NOTE` says how it was read; start-up continues. | code test |
| CFG-S6 | The report flags a deprecated name with its replacement, a setting given under both names, and an unknown `GULGRIR_*` variable, naming the closest known setting when one is a letter or two away. An unknown variable's value is never shown. | code test |
| CFG-S7 | Start-up stops when a required secret is missing or `GULGRIR_DB_PORT` is not a whole number from 1 to 65535. The report still prints, and its last line names each variable at fault and why. For a missing secret it gives a command that generates one using only `A-Z a-z 0-9 - _`. | code test |
| CFG-S8 | No secret's value appears in any log. In the report a secret's `DEFAULT` is `(none)`, its `OVERRIDE` is `(set)` or `(missing)`, and its `IN EFFECT` is `(redacted)`. | code test for the report; review for other logs |
