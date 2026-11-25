# Deployment options

Both options use the same source folders and bidding rules. The database is SQLite; keep it on durable storage and back it up. No hosting service is configured or deployed by this repository.

## Option 1: One deployment

Build the React app, then let FastAPI serve the built files and the API on one origin.

```bash
cd frontend
npm ci
npm run build
cd ../backend
uv sync --locked --no-dev
uv run --no-dev python -m app.main --host 0.0.0.0 --port 8000
```

The frontend defaults to relative `/api/...` requests. Leave `VITE_API_BASE_URL` empty and `FRONTEND_ORIGINS` unset. FastAPI serves `frontend/dist/` at `/` and `/assets`, and the API at `/api`. Put the application behind your hosting platform's HTTPS endpoint.

The deployment artifact needs `backend/` and `frontend/dist/` in their repository-relative positions. Node.js is needed during the frontend build, not when running the backend. The default database remains at the repository root; alternatively supply `--db /persistent/path/rfq.sqlite3`.

## Option 2: Separate frontend and API deployments

Deploy `frontend/dist/` to a static host. Configure the API's public origin before building:

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://api.example.com npm run build
```

`VITE_API_BASE_URL` is the backend origin, without `/api`. Vite includes it in the built JavaScript; rebuild to change it. This is public configuration, so never put secrets in it.

Deploy `backend/` separately. Enable API-only mode and allow the frontend's exact browser origin:

```bash
cd backend
uv sync --locked --no-dev
FRONTEND_ORIGINS=https://rfq.example.com uv run --no-dev python -m app.main --api-only --host 0.0.0.0 --port 8000 --db /persistent/path/rfq.sqlite3
```

Replace the example domains with your deployed origins. Use a comma-separated `FRONTEND_ORIGINS` list if needed. Origins include scheme, hostname, and any non-default port; do not include paths or trailing slashes. API-only mode does not mount or require the frontend build. `/api/rfqs`, `/docs`, and `/openapi.json` remain available; `/` returns 404.

CORS permits GET/POST requests and the Content-Type header only for configured origins. This demo has no login; CORS controls browser access and is not authentication or authorization. For separate hosting, use an API service that provides HTTPS and durable SQLite storage.

## Environment files

Each application includes `.env.example`. You can copy it to `.env` and edit it. Vite reads the frontend environment at build time. For the backend, explicitly load the file through uv:

```bash
uv run --env-file .env python -m app.main --api-only
```

Environment files are ignored by Git. The Vite development proxy is only for `npm run dev`; it does not configure a deployed static host. As an alternative to cross-origin requests, a frontend host can reverse-proxy `/api` to FastAPI and keep `VITE_API_BASE_URL` empty.
