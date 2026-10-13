# 0005. One image, with the new app as the front door

- Status: accepted
- Date: 2026-10-10

## Context

[0003](0003-strangler-migration-on-shared-database.md) runs the new app next to Django and
routes each path to whichever app serves it. The routing has to live somewhere. Installs
pull a published image and run it from their own compose file, possibly behind their own
reverse proxy. Upgrading must not need expert help (SYS-4), and no release may regress
(SYS-11). Installs other than the author's may exist and cannot be contacted.

[0002](0002-typescript-full-stack.md) chose Node LTS without naming a version or a package
manager.

## Alternatives

| Option                                        | Rejected because                                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| nginx as a separate compose service           | Every install has to edit its compose file to upgrade.                                            |
| nginx inside the image                        | A third process and a second routing language that tests don't reach. When Django goes, every install's routing changes a second time, because Node must take over the port. |
| A proxy library or `fetch` in the new app      | By default these merge `Set-Cookie` headers, follow redirects or decompress bodies; each is a regression to catch. |
| Bun as the runtime                            | No LTS line, and 1.4 (August 2026) is a fresh rewrite in Rust; both work against SYS-11. Its built-in tooling and supply-chain defaults are matched by pnpm on Node. |
| npm as the package manager                    | Runs install scripts by default and has no minimum release age.                                   |

## Decision

One image carries both apps. The new app listens on the port the image already exposes
and is the front door: it serves the paths that have moved and proxies every other request
to Django, which listens only inside the container. Moving a screen is a route change in
the new app's code.

The proxy is transitional: it exists only while both apps run side by side. It is a
hand-rolled pass-through on Node's `http` module, which streams the request and response
untouched, so retiring Django means deleting it and no install changes. `/healthz` belongs
to the new app and reports whether Django answers, for the image's health check.

The entrypoint ignores any command it is handed and always starts both apps; gunicorn
serves Django in development too. `GULGRIR_DEBUG` turns on reloading in both, so one
compose file can run everywhere.

The image runs Node 26, LTS from 2026-10-28 and supported until 2029-04-30, and installs
with pnpm.

## Consequences

- An upgrade is pulling the new image; the compose file, the exposed port and any host
  reverse proxy stay as they are.
- The image contains Python and Node, so it grows.
- One container runs two processes. If Django dies the front door keeps running and answers
  502, and the health check marks the container unhealthy, so the failure stays visible in
  the logs instead of hidden by a restart. Nothing handles the front door dying; that case
  goes away with Django.
- Existing compose files override the image's entrypoint and command with the old ones, so
  the entrypoint stays at its old path and ignores the command it receives.
- Development runs gunicorn instead of `runserver`, so it runs the server production runs.
- The front door sees every request, so a sign-in it owns can cover Django too.
- Routing is TypeScript, tested like the rest of the code.
- Revisit Bun once it has an LTS policy or a track record on the Rust codebase; Hono and
  Drizzle run on both.
