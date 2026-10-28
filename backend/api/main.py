"""Local: python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 9000."""
import logging
import os
from uuid import uuid4
import psycopg2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.api.routes import router
from backend.api.auth import router as auth_router

app = FastAPI(title='Lobster Dashboard API', version='1.0.0',
              docs_url='/api/docs', openapi_url='/api/openapi.json', redoc_url=None)
app.add_middleware(CORSMiddleware,
                   allow_origins=[s.strip() for s in os.getenv('API_ALLOWED_ORIGINS', '').split(',') if s.strip()],
                   allow_credentials=False, allow_methods=['GET','POST'],
                   allow_headers=['Authorization','Content-Type'])


@app.middleware('http')
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    return response


@app.exception_handler(psycopg2.Error)
async def database_error(request: Request, exc):
    logging.error('API database failure request_id=%s type=%s', request.state.request_id, type(exc).__name__)
    return JSONResponse(status_code=503, content={'detail': 'Database unavailable', 'request_id': request.state.request_id})


@app.exception_handler(KeyError)
async def configuration_error(request: Request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Service configuration incomplete'})


@app.get('/api/health')
def health():
    return {'status': 'ok'}


app.include_router(router)
app.include_router(auth_router)
