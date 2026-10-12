# System architecture

Gulgrir is a Django 5.2 project on PostgreSQL 16, run from one container image with
gunicorn. Stack choices are in [decisions/](decisions/README.md).

| Path                | Holds                                                    |
| ------------------- | -------------------------------------------------------- |
| `src/gulgrir/`      | project settings and URL root                            |
| `src/tracker/`      | the single app: models, views, services, templates, static |
| `src/manage.py`     | Django entry point                                       |
| `app/`              | the new TypeScript app; so far, the [configuration](configuration/architecture.md) check |
| `docker/app/`       | Dockerfile and the entrypoint that migrates before serving |

The image's entrypoint applies migrations and creates the first superuser if none exists,
stopping when its credentials are missing, then runs
the command Compose gives it. Static files are collected at build time and served by
WhiteNoise.
