# Hosting the Community Addressing editor

The editor is one Python process (FastAPI + Uvicorn) with a project folder
(`input/`, `network/`) and a database (SQLite or PostgreSQL). It has individual
invited accounts, server-enforced roles and an audit history. It is currently
designed for a small trusted editing team, not anonymous public address lookup.

## Quick start (Docker)

```bash
cd code/OSMAddressSystem
docker compose -f deploy/docker-compose.yml up -d --build       # http://127.0.0.1:8000, data in the volume "address-data"
```

The first start copies the Fotouni template (`projects/fotouni`) into the
persistent volume; later starts keep the volume. This is a staging image until
the Linux build, restore procedure and expected concurrent load have been
validated.

Before exposing the service, create the first administrator from the host. The
command prompts for the passphrase; never place it in Compose, shell history or
chat:

```bash
docker compose -f deploy/docker-compose.yml exec app \
  python -m osmaddresssystem.app account --project /data/project \
  --username admin --name "Project administrator"
```

The administrator then creates one-use invitations and assigns Viewer,
Contributor, Mapper or Administrator roles in the **Team** screen.

## On the internet

1. Start the app privately, create the first administrator and verify a backup.
2. Point a domain at the server and replace `addresses.example.org` in `deploy/Caddyfile`.
3. Run `docker compose -f deploy/docker-compose.yml --profile public up -d --build`.
4. Caddy obtains the HTTPS certificate; the application performs sign-in and authorization.
5. Only Caddy is publicly exposed on ports 80/443. Never publish the app container port directly.

## PostgreSQL instead of SQLite

SQLite (write-ahead log) is reasonable for an initial 2-3-editor pilot. For a
shared server database, set `ADDRESS_DB_URL=postgresql+psycopg://...` using a
secret supplied by the host, uncomment the Compose setting and start the
`postgres` profile. Do not keep a real password in the repository.

## Without Docker

`uv sync --extra app --extra planning --extra server`, then use
`deploy/address-app.service` or run the serve command behind Caddy/nginx. Set
`ADDRESS_ROOT_PATH=/prefix` only when the proxy strips that prefix. Set
`ADDRESS_FORWARDED_ALLOW_IPS` to the proxy's IP/network; `*` is acceptable only
when the application port is unreachable from untrusted networks.

## Rules

* **One worker only** (the computed network is kept in memory). Do not start uvicorn with `--workers`.
* **Health**: `GET /api/health` returns the database, the revision and whether a computation runs (used by the Docker health check).
* **Backups**: `deploy/backup.sh PROJECT BACKUPS` from cron uses SQLite's backup API or `pg_dump`. Back up `input/`, `network/` and deployment configuration too. Prove restoration into a new directory before the pilot.
* **Uploads** (KML etc.) are limited to 60 MB by the app and by the proxy.
* To start a different area: `python -m osmaddresssystem.app init --project DIR --streets-osm ... --area ... --buildings ...` then `setup`.
* Run one isolated project process/data root per community until multi-project administration is designed.
* The live editor API is not the future public integration API. Publish an approved, versioned snapshot for ride-pooling, marketplace and public lookup clients.
