# gulgrir

Every backlog in one place — books, films, shows, games, music, anime, manga, light novels
and personal projects — with help rotating through them so binging one thing doesn't bury
the rest. Self-hosted, for people who keep their data on their own hardware.

It is in daily use and mid-migration: a TypeScript app is replacing the Django one screen by
screen, on the same database
([0003](docs/system/decisions/0003-strangler-migration-on-shared-database.md)).

## Quickstart

```
mkdir gulgrir && cd gulgrir
curl -fsSLO https://raw.githubusercontent.com/TheBitBanger/gulgrir/dev/compose.yml
# write .env as in docs/operations/install.md
docker compose up -d
```

Then open `http://localhost:8765`.

## Where to go next

- [docs/](docs/README.md) — what the system must do, how to work on it, how to run it
- [docs/operations/install.md](docs/operations/install.md) — the full install guide
- [docs/development/](docs/development/README.md) — working on the code

| Directory  | Holds                                          |
| ---------- | ---------------------------------------------- |
| `src/`     | the Django project (`gulgrir`) and app (`tracker`) |
| `docker/`  | the image's Dockerfile and entrypoint          |
| `scripts/` | build helpers                                  |
| `docs/`    | all documentation                              |
