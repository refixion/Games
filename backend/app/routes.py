from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import asyncpg
import secrets
import hashlib

from .config import settings
from .database import get_pool
from .email import send_secret_email
from .schemas import GameSelectIn, JoinIn, StatusIn, ToggleIn, VoteIn

router = APIRouter(prefix='/api')

GAME_PRESETS = [
    {'id': 'murder_mystery', 'label': 'Murder Mystery', 'description': 'Een tafel vol verdachten, geheimen en een zaak die opgelost moet worden.', 'type': 'Murder mystery', 'roles': ['Murderer', 'Detective', 'Citizen'], 'theme': {'primary': '#b45309', 'accent': '#fbbf24'}},
    {'id': 'the_heist', 'label': 'The Heist', 'description': 'Plan een gewaagde kraak terwijl niemand zeker weet wie aan welke kant staat.', 'type': 'Team strategy', 'roles': ['Boss', 'Inside Man', 'Banker', 'Operative'], 'theme': {'primary': '#2563eb', 'accent': '#f59e0b'}},
    {'id': 'the_investigation', 'label': 'The Investigation', 'description': 'Leg getuigenissen, documenten en tegenstrijdige motieven naast elkaar.', 'type': 'Investigation', 'roles': ['Detective', 'Witness', 'Archivist', 'Suspect'], 'theme': {'primary': '#0f766e', 'accent': '#99f6e4'}},
]
VALID_STATUSES = {'draft', 'registration_open', 'registration_closed', 'game_started', 'finished'}


def preset_exists(preset_id: str):
    return next((preset for preset in GAME_PRESETS if preset['id'] == preset_id), None)


async def get_game_state(conn):
    row = await conn.fetchrow('SELECT id, game_name, game_preset, registration_open, voting_active, status, theme, updated_at FROM game_state ORDER BY id LIMIT 1')
    return dict(row) if row else None


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
        'presets': GAME_PRESETS,
    }


@router.get('/game-state')
async def game_state():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return await get_game_state(conn)
    finally:
        await pool.close()


@router.post('/join')
async def join(payload: JoinIn):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await conn.fetchrow('SELECT registration_open, game_preset FROM game_state ORDER BY id LIMIT 1')
            if state and not state['registration_open']:
                return JSONResponse(status_code=400, content={'success': False, 'message': 'De inschrijving is gesloten.'})
            try:
                await conn.execute(
                    'INSERT INTO players(name, email, game_preset, status) VALUES($1, $2, $3, $4)',
                    payload.name,
                    str(payload.email),
                    state['game_preset'] if state else 'murder_mystery',
                    'registered',
                )
            except asyncpg.UniqueViolationError:
                return JSONResponse(status_code=400, content={'success': False, 'message': 'Deze email is al aangemeld.'})
    finally:
        await pool.close()
    return {'success': True, 'message': 'Je bent aangemeld.'}


@router.post('/game/select')
async def select_game(payload: GameSelectIn, request: Request):
    await admin_check(request)
    preset = preset_exists(payload.game_preset)
    if not preset:
        raise HTTPException(status_code=400, detail='Onbekende game.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('UPDATE game_state SET game_preset=$1, game_name=$2, theme=$3, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', preset['id'], preset['label'], preset['theme'])
            return await get_game_state(conn)
    finally:
        await pool.close()


@router.post('/game/status')
async def set_status(payload: StatusIn, request: Request):
    await admin_check(request)
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail='Ongeldige spelstatus.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            registration_open = payload.status == 'registration_open'
            await conn.execute('UPDATE game_state SET status=$1, registration_open=$2, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', payload.status, registration_open)
            return await get_game_state(conn)
    finally:
        await pool.close()


@router.post('/poll/toggle')
async def toggle_poll(payload: ToggleIn, request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('UPDATE game_state SET voting_active=$1, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', payload.active)
            return {'active': payload.active}
    finally:
        await pool.close()


@router.post('/poll/vote')
async def vote(payload: VoteIn, request: Request):
    if not preset_exists(payload.game_preset):
        raise HTTPException(status_code=400, detail='Onbekende game.')
    token = request.headers.get('x-vote-token', '')
    if not token:
        raise HTTPException(status_code=400, detail='Stemtoken ontbreekt.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            active = await conn.fetchval('SELECT voting_active FROM game_state ORDER BY id LIMIT 1')
            if not active:
                raise HTTPException(status_code=400, detail='De poll is niet actief.')
            voter_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
            try:
                await conn.execute('INSERT INTO poll_votes(game_preset, voter_hash) VALUES($1, $2)', payload.game_preset, voter_hash)
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail='Je hebt al gestemd.')
            return {'success': True, 'message': 'Stem ontvangen.'}
    finally:
        await pool.close()


@router.get('/poll/results')
async def poll_results(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT game_preset, count(*)::int AS count FROM poll_votes GROUP BY game_preset ORDER BY count DESC')
            return {'results': [dict(row) for row in rows], 'total': sum(row['count'] for row in rows)}
    finally:
        await pool.close()


@router.post('/poll/reset')
async def reset_poll(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('TRUNCATE poll_votes')
        return {'success': True, 'message': 'Stemmen gereset.'}
    finally:
        await pool.close()


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

