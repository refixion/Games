import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield

app = FastAPI(title='Secret Game API', lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get('FRONTEND_URL', 'http://localhost:5173').split(',')
    if origin.strip()
]
allowed_origins.append('http://localhost:5173')
allowed_origins.append('http://127.0.0.1:5173')

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(set(allowed_origins)),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)
