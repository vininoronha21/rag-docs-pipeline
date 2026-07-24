ptdddu

# Deployment Guide

This guide defines the hosted contracts for the Render backend, Vercel frontend,
and Neon PostgreSQL database. Keep real secret values in provider dashboards only.

## Render Backend

Render deploys the backend from `render.yaml` with the Docker context at the
repository root and `backend/Dockerfile` as the image definition.

- Health check path: `/api/health`
- Render plan: `free` (free tier; cold starts are expected)
- Runtime port: `${PORT:-8000}`
- Start command: `python -m alembic upgrade head` followed by one Uvicorn process
- Runtime process: `python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log`
- Access logs: disabled with `--no-access-log` so client addresses and request paths are not retained by Uvicorn.

Set these Render environment variables before the first deploy:

| Variable                   | Source                  | Notes                                     |
| -------------------------- | ----------------------- | ----------------------------------------- |
| `ENVIRONMENT`            | Literal`production`   | Non-secret runtime mode.                  |
| `ADMIN_SECRET`           | Render generated secret | Required by production settings.          |
| `DATABASE_URL`           | Manual secret from Neon | Async SQLAlchemy URL for API runtime.     |
| `MIGRATION_DATABASE_URL` | Manual secret from Neon | Sync SQLAlchemy URL for Alembic.          |
| `ALLOWED_ORIGINS`        | Manual exact origin     | Set to the production Vercel origin only. |

Do not add `NEXT_PUBLIC_BACKEND_URL` to Render. It is a frontend build variable.

## Neon Database

Create a Neon PostgreSQL database, then enable pgvector once with a privileged
database role:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Use driver-specific TLS URLs. The runtime URL must use asyncpg and `ssl`:

```text
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<neon-host>/<database>?ssl=require
```

The migration URL must use psycopg and `sslmode`:

```text
MIGRATION_DATABASE_URL=postgresql+psycopg://<user>:<password>@<neon-host>/<database>?sslmode=require
```

Run Alembic with the migration URL available in the environment:

```bash
MIGRATION_DATABASE_URL='postgresql+psycopg://<user>:<password>@<neon-host>/<database>?sslmode=require' python -m alembic upgrade head
```

Do not derive the migration URL from `DATABASE_URL`; the app validates the two
driver contracts separately.

## Vercel Frontend

Create the Vercel project from this repository and set the project root to the
frontend directory.

- Project root: `frontend`
- Install command: `npm ci`
- Build command: `if [ -z "$NEXT_PUBLIC_BACKEND_URL" ]; then printf 'NEXT_PUBLIC_BACKEND_URL must be set in the Vercel project environment.\n' >&2; exit 1; fi; npm run build`
- Public backend URL: configure `NEXT_PUBLIC_BACKEND_URL` in the Vercel project environment.

Set `NEXT_PUBLIC_BACKEND_URL` before building. It is public and is baked into
the Next.js client bundle during `npm run build`. `frontend/vercel.json`
intentionally does not commit a value and its build command fails when the
provider environment is missing the variable.

## Production CORS

Set Render `ALLOWED_ORIGINS` to the exact Vercel production origin. Do not use a
wildcard origin and do not include preview URLs unless they are intentionally
approved.

```text
ALLOWED_ORIGINS=["<vercel-production-origin>"]
```

The URL must include the scheme, host, and any non-default port. Do not include
paths.

## Local Container Check

Use the compose file for local verification. It keeps the async runtime URL and
sync migration URL separate while passing `NEXT_PUBLIC_BACKEND_URL` at frontend
image build time.

```bash
docker compose build backend frontend
docker compose up -d postgres backend frontend
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:8000/api/ready
curl --fail http://localhost:3000/
```
