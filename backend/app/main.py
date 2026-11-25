"""FastAPI application. Run from backend/: uv run python -m app.main --seed"""
import argparse
import os
import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .auction import PROJECT_ROOT, Invalid, Store, seed, utcnow
from .models import QuoteCreate, RFQCreate


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDependency = Annotated[Store, Depends(get_store)]
FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'


def create_app(
    db_path=PROJECT_ROOT / 'rfq.sqlite3',
    *,
    seed_demo=False,
    clock=utcnow,
    serve_frontend=True,
    allowed_origins=None,
):
    @asynccontextmanager
    async def lifespan(application):
        application.state.store = Store(db_path, clock)
        if seed_demo:
            seed(application.state.store)
        yield

    app = FastAPI(title='British RFQ', version='1.0.0', lifespan=lifespan)
    if allowed_origins is None:
        allowed_origins = [
            origin.strip()
            for origin in os.getenv('FRONTEND_ORIGINS', '').split(',')
            if origin.strip()
        ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=['GET', 'POST'],
            allow_headers=['Content-Type'],
        )

    @app.exception_handler(Invalid)
    async def business_error(request, exc):
        return JSONResponse(status_code=exc.status, content={'error': str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Preserve the frontend's error envelope while FastAPI validates the inputs.
        messages = []
        for error in exc.errors():
            field = '.'.join(str(part) for part in error['loc'] if part != 'body')
            messages.append(f"{field}: {error['msg']}" if field else error['msg'])
        return JSONResponse(status_code=422, content={'error': '; '.join(messages)})

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, exc):
        return JSONResponse(status_code=503, content={'error': 'Database temporarily unavailable. Please retry.'})

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={'error': str(exc.detail)}, headers=exc.headers)

    @app.get('/api/rfqs')
    def list_rfqs(store: StoreDependency):
        return store.list()

    @app.post('/api/rfqs', status_code=201)
    def create_rfq(payload: RFQCreate, store: StoreDependency):
        return {'id': store.create(payload)}

    @app.get('/api/rfqs/{rfq_id}')
    def get_rfq(rfq_id: int, store: StoreDependency):
        return store.detail(rfq_id)

    @app.post('/api/rfqs/{rfq_id}/quotes', status_code=201)
    def submit_quote(rfq_id: int, payload: QuoteCreate, store: StoreDependency):
        return store.bid(rfq_id, payload)

    if serve_frontend:
        @app.get('/', include_in_schema=False)
        def frontend():
            index = FRONTEND_DIST / 'index.html'
            if not index.is_file():
                raise HTTPException(status_code=503, detail='Frontend is not built. Run npm ci and npm run build in frontend/.')
            return FileResponse(index)

        app.mount('/assets', StaticFiles(directory=FRONTEND_DIST / 'assets', check_dir=False), name='assets')

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--api-only', action='store_true', help='Run only the API; host React separately.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default=str(PROJECT_ROOT / 'rfq.sqlite3'))
    parser.add_argument('--seed', action='store_true', help='Add sample RFQs if the database is empty.')
    args = parser.parse_args()
    uvicorn.run(create_app(args.db, seed_demo=args.seed, serve_frontend=not args.api_only),
                host=args.host, port=args.port)


if __name__ == '__main__':
    main()
