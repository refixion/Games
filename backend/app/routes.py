from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import asyncpg
import secrets

from .config import settings
from .database import get_pool
from .email import send_secret_email
from .schemas import GenericResponse, JoinIn

router = APIRouter(prefix='/api')


async def admin_check(request: Request):
    header = request.headers.get('x-admin-password', '')
    if not header or header != settings.admin_password:
        raise HTTPException(status_code=401, detail='Unauthorized')


@router.get('/health')
async def health():
    return {'status': 'ok', 'app': settings.app_name}


@router.get('/game-config')
async def game_config():
    return {
        'game_name': settings.app_name,
        'presets': [
            {'id': 'murder_mystery', 'label': 'Murder Mystery', 'type': 'murder_mystery', 'roles': ['Murderer', 'Detective', 'Citizen'], 'theme': {'primary': '#7f1d1d', 'accent': '#fbbf24'}},
            {'id': 'the_heist', 'label': 'The Heist', 'type': 'the_heist', 'roles': ['Boss', 'Inside Man', 'Banker', 'Operative'], 'theme': {'primary': '#1d4ed8', 'accent': '#f59e0b'}},
            {'id': 'the_investigation', 'label': 'The Investigation', 'type': 'the_investigation', 'roles': ['Detective', 'Witness', 'Archivist', 'Suspect'], 'theme': {'primary': '#0f766e', 'accent': '#e2e8f0'}}
        ]
    }


@router.post('/join')
async def join(payload: JoinIn):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    'INSERT INTO players(name, email, game_preset, status) VALUES($1, $2, $3, $4)',
                    payload.name,
                    str(payload.email),
                    'murder_mystery',
                    'registered',
                )
            except asyncpg.UniqueViolationError:
                return JSONResponse(status_code=400, content={'success': False, 'message': 'Deze email is al aangemeld.'})
    finally:
        await pool.close()
    return {'success': True, 'message': 'Je bent aangemeld.'}


@router.get('/players/count')
async def players_count(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT count(*)::int as c FROM players')
        return {'count': row['c'] if row else 0}
    finally:
        await pool.close()


@router.get('/players')
async def list_players(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT id, name, email, role, target, status, game_preset FROM players ORDER BY created_at ASC')
        return {'players': [dict(row) for row in rows]}
    finally:
        await pool.close()


@router.post('/draw')
async def draw(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT id, name, email FROM players ORDER BY created_at ASC')
            if not rows:
                raise HTTPException(status_code=400, detail='Geen deelnemers')

            chosen = secrets.choice(rows)
            role_name = 'Geheime speler'
            secret_text = 'Je bent succesvol ingeschreven voor dit geheim spel. Houd deze informatie geheim.'
            try:
                await send_secret_email(
                    chosen['email'],
                    player_name=chosen['name'],
                    role_name=role_name,
                    game_name=settings.app_name,
                    secret_info=secret_text,
                )
            except Exception as exc:  # pragma: no cover
                raise HTTPException(status_code=500, detail=f'Fout bij verzenden email: {str(exc)}') from exc

            await conn.execute('UPDATE players SET role=$1, updated_at=now() WHERE id=$2', role_name, chosen['id'])
        return {'success': True, 'message': 'De geheime speler is geïnformeerd.'}
    finally:
        await pool.close()


@router.post('/reset')
async def reset(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('TRUNCATE players')
        return {'success': True, 'message': 'Alle deelnemers verwijderd.'}
    finally:
        await pool.close()

