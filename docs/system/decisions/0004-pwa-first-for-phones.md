# 0004. Phones get an installable web app first

- Status: accepted
- Date: 2026-10-07

## Context

SYS-7 requires use from both desktop and phone. The key phone uses are:

- starting and stopping timers away from the desk;
- checking whether something was already consumed;
- recommending something to someone.

## Alternatives

| Option                                          | Rejected because                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------- |
| Responsive website only                         | It can't be installed and has weaker notification support.                |
| Native app, or a native wrapper such as Capacitor from day one | App stores, a second build pipeline, and release overhead, for features the web already covers. |

## Decision

The UI from [0002](0002-typescript-full-stack.md) is responsive and installable as a
Progressive Web App, including web push notifications. A native wrapper is considered only
when a needed phone capability is missing from the web.

## Consequences

- One codebase serves desktop and phone.
- Installing the app and receiving push notifications requires HTTPS. Instances behind a VPN
  need a reverse proxy with TLS, which belongs in the operations docs.
- Working offline stays out of scope. If it is ever needed, a PWA can add it.
