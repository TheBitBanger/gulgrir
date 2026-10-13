# System design

Contracts and Verification bind; Structure describes the system as built.

## Contracts

### Upgrading

| Serves         | Contract |
| -------------- | -------- |
| SYS-4, SYS-11  | An install upgrades by pulling the new image, with its compose file and `.env` unchanged. The image brings its own entrypoint, which starts both apps whatever command it is handed. |
| SYS-4, SYS-11  | A compose file that still sets the old `entrypoint` and `command` gets the image's defaults anyway, and the start-up log says those lines are deprecated and can be removed. This compatibility is removed in the first release after 2027-10-10. |
| SYS-4, SYS-11  | The app answers on the host port the compose file maps to the container, 8765 by default. |
| SYS-10         | Starting a release on a database last used by the previous release keeps every row of every existing table, and the old screens show it as before. |
| SYS-10         | Migrations apply on start, before the app serves requests. |
| SYS-4          | Everything both apps write to standard output and standard error appears in the container log, Django's as before. |
| SYS-11         | With `GULGRIR_DEBUG` true, each app restarts itself when its source files change; otherwise neither watches its files. |

### Routing

| Serves  | Contract |
| ------- | -------- |
| SYS-11  | A request for a path the new app does not serve reaches Django with its method, path, query, headers and body, and the client gets Django's response unchanged: status, headers (every `Set-Cookie` included), redirects not followed, and body. |
| SYS-11  | Django sees the client's original `Host`, and the `X-Forwarded-Proto` the front door received, or `http` when there was none. Allowed hosts, CSRF checks and the secure-proxy setting behave as without the front door. |
| SYS-11  | If Django refuses the connection, the client gets a 502 at once. |
| SYS-4   | `GET /healthz` is answered by the new app: 200 when Django answers with a status below 500; 503 when Django refuses the connection or answers 5xx, with a body naming the app that is down. The image's health check calls it, so `docker ps` shows the container as unhealthy; the image never restarts or stops itself because of it. |
| SYS-11  | A path moves to the new app only when its screen covers everything the Django screen did. A release with no moved paths is valid. |

### Data ownership

| Serves  | Contract |
| ------- | -------- |
| SYS-10  | The new app never creates, alters or drops a table Django's migrations own. Its own migrations touch only its own tables. |

## Structure

Gulgrir is a Django 5.2 project on PostgreSQL 16, being replaced screen by screen with a
TypeScript app on Node 26 ([0003](decisions/0003-strangler-migration-on-shared-database.md)).
Both run in one container image. Stack choices are in [decisions/](decisions/README.md).

| Path                | Holds                                                    |
| ------------------- | -------------------------------------------------------- |
| `src/gulgrir/`      | project settings and URL root                            |
| `src/tracker/`      | the single app: models, views, services, templates, static |
| `src/manage.py`     | Django entry point                                       |
| `app/`              | the new TypeScript app: the [configuration](configuration/design.md) check and the front door |
| `docker/app/`       | Dockerfile and the entrypoint that starts both apps      |

### Two processes, one front door

The new app's front door (`app/src/front-door.ts`) listens on 8765 and passes every
request through to gunicorn, which serves Django on `127.0.0.1:8000` inside the container
([0005](decisions/0005-one-image-with-the-new-app-as-front-door.md)). It is Node's `http`
module streaming raw headers and bodies both ways, so nothing is merged, decompressed or
followed. It answers `/healthz` itself by requesting Django's `/login/`, and the image's
`HEALTHCHECK` calls it.

### Start-up

The entrypoint ignores any command it is handed, logging that the old one can be removed,
and then, in order:

| Step | Does                                                                                   | On failure           |
| ---- | -------------------------------------------------------------------------------------- | -------------------- |
| 1    | Runs the configuration check, which prints its report and exports Django's environment | stops                |
| 2    | Waits up to 60 seconds for the database to accept connections                         | goes on to step 3    |
| 3    | Applies migrations                                                                     | stops                |
| 4    | Creates the first superuser if none exists                                             | stops                |
| 5    | Starts gunicorn in the background                                                      | the front door answers 502 |
| 6    | Replaces itself with the front door, which becomes the container's main process        | the container exits  |

With `GULGRIR_DEBUG` true, gunicorn gets `--reload` and Node `--watch`. Both write to the
container log. Nothing restarts gunicorn if it dies: the front door keeps answering 502 and
the health check turns unhealthy, so the failure stays visible.

### Image

Node and pnpm are installed in the Dockerfile's `base` stage, so the `runtime` and `qa`
images both carry them; the CSS linters are installed only in `qa`. The image installs the
new app's production dependencies and runs its `.ts` files directly with Node's type
stripping, with no build step. Static files are collected at build time and served by
WhiteNoise.

## Verification

Tests named `smoke` are checks in `scripts/smoke-test-image.sh`, run by
`make smoke-test-image`; the others are in `app/test/front-door.test.ts`.

| ID      | Serves         | Method        | Check |
| ------- | -------------- | ------------- | ----- |
| SYS-V1  | SYS-4, SYS-11  | test          | smoke: "the new app answers /healthz on the mapped port (SYS-V1)" — the image runs with no entrypoint or command given |
| SYS-V2  | SYS-4, SYS-11  | test          | smoke: "Django answers through the front door (SYS-V2)" |
| SYS-V3  | SYS-4, SYS-11  | demonstration | Once: start the image with the old compose file's `entrypoint` and `command`; the app answers on 8765 and the log names both lines as deprecated. |
| SYS-V4  | SYS-10         | demonstration | Rehearsal: restore a copy of the production backup into dev, start the release on it, and compare row counts of every table and the old screens with the previous release. |
| SYS-V5  | SYS-10         | inspection    | The entrypoint runs `migrate` in the foreground under `set -e` before starting either server. |
| SYS-V6  | SYS-4          | test          | smoke: "the configuration report is in the container log (SYS-V6)" and "gunicorn's output is in the container log (SYS-V6)" |
| SYS-V7  | SYS-11         | demonstration | Once: in the dev stack with `GULGRIR_DEBUG` true, edit a file under `src/` and one under `app/src/`; the log shows gunicorn and Node restarting. With it false, neither restarts. |
| SYS-V8  | SYS-11         | test          | "a path the new app does not serve reaches Django (SYS-V8)" |
| SYS-V9  | SYS-11         | test          | "Django sees the request as the client sent it (SYS-V9)" |
| SYS-V10 | SYS-11         | test          | "Django not answering (SYS-V10)" |
| SYS-V11 | SYS-4          | test          | "GET /healthz (SYS-V11)" |
| SYS-V12 | SYS-4          | test          | smoke: "the image's health check reports healthy (SYS-V12)", "with Django dead the health check reports unhealthy (SYS-V12)" and "with Django dead the container keeps running (SYS-V12)" |
| SYS-V13 | SYS-11         | inspection    | Every path the new app serves has a screen covering everything its Django screen did. |
| SYS-V14 | SYS-10         | inspection    | The new app has no database code; once it gets a table, this becomes a test. |
