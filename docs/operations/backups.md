# Backups and restores

The optional `backup` service runs the standalone
[kethuroth](https://github.com/TheBitBanger/kethuroth) image, which documents every option.
It writes database dumps to `./backups` on the host. It creates the directory itself, but
creating it first and setting `BACKUP_UID` / `BACKUP_GID` avoids root-owned files.

## Back up now

```
docker compose run --rm backup backup
```

## Restore

Stop the app, and any other service that connects to the database:

```
docker compose stop app
```

Restore the dump, then start the app:

```
docker compose run --rm backup restore /backups/<dump file>.dump
docker compose start app
```

If a service named here doesn't exist in your version of the stack, skip it; the docs at
your image's tag match your stack.
