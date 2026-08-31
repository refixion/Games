import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router

app = FastAPI(title='Secret Game API')

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
