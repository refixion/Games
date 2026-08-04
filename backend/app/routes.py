from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from .schemas import JoinIn, GenericResponse
from .config import settings
import asyncpg
import secrets
from .database import get_pool
from .email import send_secret_email

router = APIRouter()

async def admin_check(request: Request):
    header = request.headers.get('x-admin-password','')
    if not header or header != settings.admin_password:
        raise HTTPException(status_code=401, detail='Unauthorized')

@router.post('/join')
async def join(payload: JoinIn):
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute('INSERT INTO players(name,email) VALUES($1,$2)', payload.name, payload.email)
        except asyncpg.UniqueViolationError:
            return JSONResponse(status_code=400, content={ 'success': False, 'message': 'Deze email is al aangemeld.' })
    return { 'success': True, 'message': 'Je bent aangemeld.' }

@router.get('/players/count')
async def players_count(request: Request):
    # admin protected
    await admin_check(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT count(*)::int as c FROM players')
    return { 'count': row['c'] }

@router.post('/draw')
async def draw(request: Request):
    await admin_check(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT id,name,email FROM players')
        if not rows:
            raise HTTPException(status_code=400, detail='Geen deelnemers')
        # choose securely
        chosen = secrets.choice(rows)
        # send email
        try:
            await send_secret_email(chosen['email'])
        except Exception as e:
            raise HTTPException(status_code=500, detail='Fout bij verzenden email')
    return { 'success': True, 'message': 'De geheime speler is geïnformeerd.' }

@router.post('/reset')
async def reset(request: Request):
    await admin_check(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('TRUNCATE players')
    return { 'success': True, 'message': 'Alle deelnemers verwijderd.' }

