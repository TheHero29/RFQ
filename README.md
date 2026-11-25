# British RFQ

British Auction RFQs with a React frontend, FastAPI backend, and SQLite. The two applications have separate source code, dependency files, and development commands. Both a combined deployment and separate frontend/API deployments are supported. See [deployment options](docs/DEPLOYMENT.md).

## Repository layout

```text
British_RFQ/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI routes and startup
│   │   ├── models.py        # Pydantic request models
│   │   └── auction.py       # Bidding rules and SQLite transactions
│   ├── tests/
│   ├── schema.sql
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   │   ├── components/     # Auction pages, forms, shared UI
│   │   ├── App.jsx         # Navigation and data refresh
│   │   ├── api.js          # HTTP requests
│   │   └── format.js       # Price/date formatting
│   ├── package.json
│   └── vite.config.js
└── docs/
    ├── HLD.md
    ├── SCHEMA.md
    └── architecture.svg
```

## Quick start

Requires uv, Python 3.11+, and Node.js 22.12+. From the repository root:

```bash
cd frontend
npm ci
npm run build
cd ../backend
uv sync --locked
uv run python -m app.main --seed
```

The frontend build is generated and is not tracked in Git. The downloadable submission ZIP includes a prebuilt `frontend/dist/`; when using that ZIP, you can go straight to the backend commands.

Open **http://127.0.0.1:8000**. API documentation is at **http://127.0.0.1:8000/docs**, with the OpenAPI schema at `/openapi.json`.

`--seed` adds three example RFQs only when the database is empty. Their schedules are relative to the initial seed time and do not reset on restart. Leave out `--seed` to start empty. Stop with Ctrl+C.

The database is created at `British_RFQ/rfq.sqlite3`, outside the source folders, and persists across restarts. Runtime database files are excluded from Git. To use another database or port:

```bash
uv run python -m app.main --port 8080 --db /path/to/another.sqlite3
```

uv manages `backend/.venv` using `backend/pyproject.toml` and `backend/uv.lock`. No environment activation is required. The test client is in the default `dev` dependency group. For runtime-only dependencies, use `uv sync --locked --no-dev` and `uv run --no-dev python -m app.main --seed`.

## Develop frontend and backend separately

Run FastAPI in one terminal:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Run Vite in another terminal. Use Node.js 22.12+; `nvm use` in `frontend/` selects Node 22 if you use nvm.

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite. It proxies `/api` requests to FastAPI on port 8000. This proxy is for development. For separate production hosting, set `VITE_API_BASE_URL` before building React, configure `FRONTEND_ORIGINS` on FastAPI, and start the backend with `--api-only`. Exact commands are in [deployment options](docs/DEPLOYMENT.md).

## Build for a single deployment

```bash
cd frontend
npm run build
cd ../backend
uv run python -m app.main
```

Vite outputs `frontend/dist/`, which FastAPI serves alongside the API. Rebuild after editing React source. React/Vite versions are pinned in `frontend/package.json` and `frontend/package-lock.json`. Generated builds, environments, dependency directories, and runtime databases are ignored by Git.

## Deliverables

| Assignment deliverable | Location |
| --- | --- |
| HLD and architecture diagram | `docs/HLD.md`, `docs/architecture.svg` |
| Both deployment options | `docs/DEPLOYMENT.md` |
| Database schema | `backend/schema.sql`, `docs/SCHEMA.md` |
| Backend | `backend/app/` |
| Frontend | `frontend/src/` |
| Backend tests | `backend/tests/` |

## Try it

1. Create an RFQ with start now, close a few minutes ahead, and forced close later. Enable British Auction, set X = 10 and Y = 5, and select all three triggers.
2. Submit Carrier A: freight 100, origin 0, destination 0, transit 3 days, and future quote validity. A becomes L1; the first quote does not extend.
3. Submit Carrier B at 120. It becomes L2; the deadline does not move.
4. Submit Carrier B again at 90. B becomes L1 and the deadline extends once, even though all three triggers match.
5. Try Carrier C at 90. It is rejected because a current total of 90 already exists.
6. Inspect the rankings, original/current/forced deadlines, complete quote history, and activity log. Search and status filters are on the listing page.

The UI refreshes every five seconds and updates countdowns every second. The server is authoritative; an auction may close between a UI refresh and a submission, in which case the server rejects the bid.

## Bidding decisions

- Rank by **freight + origin + destination** charges, in the RFQ's single currency. Store money as integer cents/paise, with at most two input decimals. No currency conversion.
- Each supplier's **latest accepted quote** determines its rank. Preserve all earlier quotes in the price-sorted history. L1 is lowest, L2 second lowest, etc.
- A revision must be strictly lower than that supplier's previous total. A supplier can submit a valid quote without beating L1.
- Reject a total equal to another supplier's **current** total. A superseded historical quote does not block that amount.
- Supplier identity is the entered carrier name, normalized for whitespace, Unicode compatibility, and case. This is a single-workspace demo with no login or identity verification; changing the name represents another supplier.
- Multiple triggers use **OR**. A bid triggers **at most one** extension. It must beat the **previous auction-wide lowest total**, fall in the **current** close window, and match an enabled trigger. First bid never extends because there is no previous lowest.
- A rank change means an existing supplier moves to a different numeric position. A first-time entrant counts if it displaces an existing supplier. L1 change means a different supplier takes first place. A leader improving its own price is not an L1/rank change; it can still match “bid received”.
- Every qualifying bid adds Y minutes to the current close, capped at forced close. The updated close determines the next trigger window. Multiple matches do not multiply Y. At the cap, further valid bids are accepted until that deadline, but no extension is logged when no time can be added.
- Bid start is inclusive, current close is exclusive. Window start (`close - X`) is inclusive. Forced close must be strictly after the original close and can equal an extended current close.
- Status: Scheduled before start; Active during bidding; Closed after a natural deadline; Force Closed only if the auction actually reached the forced cap. A naturally closed auction stays Closed later.
- Standard RFQs have fixed closing times; disabling British Auction disables all extensions.
- Quote validity must be in the future when submitted; charges are nonnegative with a positive total; transit time is a positive whole number of days. Expiration does not retroactively remove a quote or its rank. Pickup/service date is required; the brief specifies no additional relation to validity or bidding dates.
- The API requires timezone-aware timestamps and stores UTC milliseconds. The browser converts local form input to UTC and displays dates in the device timezone.

## Tests

From `backend/`, run:

```bash
uv run --locked python -m unittest discover -s tests -v
```

33 tests cover the auction rules, concurrent submissions, deadline boundaries, persistence, request validation, API documentation, seeding, serving the React build, API-only operation, and allowed/disallowed CORS origins. The HTTP tests expect `frontend/dist/` to exist; run `npm run build` from `frontend/` if it is absent.

To run only the auction rule tests:

```bash
uv run --locked python -m unittest discover -s tests -p test_auction.py -v
```

## Scope

Intentionally kept simple for the assignment: one process, three tables, four API operations, basic React components/hooks, and browser polling. Authentication/roles, multiple buyers, invitation management, notifications, award/payment flows, distributed deployment, and production hardening are outside this demo. See `docs/HLD.md` for concurrency and scale boundaries.

Dependency management reference: [uv projects](https://docs.astral.sh/uv/guides/projects/).
