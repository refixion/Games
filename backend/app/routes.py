import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .config import settings
from .database import get_pool
from .email import build_secret_email, send_secret_email
from .ai_service import AIProviderUnavailable, GeneratedGame, ai_service
from .schemas import DurationIn, GenerateIn, GameSelectIn, JoinIn, PollIn, StatusIn, SuspicionVoteIn, ToggleIn, VoteIn

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api')

GAME_CONFIGS: dict[str, dict[str, Any]] = {
    'murder_mystery': {
        'id': 'murder_mystery', 'name': 'Murder Mystery', 'type': 'Mysterie',
        'description': "Een moordzaak vol geheimen, alibi's en tegenstrijdige aanwijzingen.",
        'goal': 'Ontmasker de Murderer voordat de zaak wordt gesloten.',
        'rules': ['Deel alleen informatie die jouw rol mag delen.', 'De Detective leidt het onderzoek.', 'De Murderer wint als de verdenking op een Citizen blijft.'],
        'steps': ['Ontvang je rol', 'Onderzoek de clues', "Bespreek alibi's", 'Stem een verdachte weg'],
        'roles': [
            {'name': 'Murderer', 'description': 'Je hebt het misdrijf gepleegd en moet uit handen van de groep blijven.', 'personal_info': 'Je was als laatste in de archiefkamer.', 'clues': ['Een rode draad is gevonden bij de achterdeur.', 'Je kent het echte tijdstip van de moord.'], 'instructions': 'Ontken rustig, stuur verdenking richting een ander en vertel je geheime tijdstip niet.'},
            {'name': 'Detective', 'description': 'Jij verzamelt verklaringen en probeert de dader logisch aan te wijzen.', 'personal_info': 'Je bezit een sleutel die niet bij het slachtoffer hoort.', 'clues': ['De klok in de hal loopt zeven minuten achter.', 'Een getuige verzwijgt een naam.'], 'instructions': 'Deel je conclusies, maar bewaar je sterkste aanwijzing voor het juiste moment.'},
            {'name': 'Citizen', 'description': 'Je bent een oplettende aanwezige die de waarheid kan helpen vinden.', 'personal_info': 'Je zag iemand gehaast de hal verlaten.', 'clues': ['Er ontbreekt een handschoen.', 'Het raam stond van binnen open.'], 'instructions': 'Vertel wat je zag zonder je vermoedens als feiten te presenteren.'},
        ],
        'theme': {'primary': '#9f1239', 'accent': '#f59e0b'},
    },
    'the_heist': {
        'id': 'the_heist', 'name': 'The Heist', 'type': 'Teamstrategie',
        'description': 'Een gewaagde kraak waarin vertrouwen net zo waardevol is als de buit.',
        'goal': 'Voltooi de kraak en ontdek wie het plan saboteert.',
        'rules': ['Bespreek openbare informatie hardop.', 'Geheime clues deel je alleen als dat strategisch slim is.', 'De Boss bepaalt het plan, maar iedereen heeft een eigen agenda.'],
        'steps': ['Lees je briefing', 'Maak een plan', 'Controleer de kluis', 'Onthul de saboteur'],
        'roles': [
            {'name': 'Boss', 'description': 'Jij stuurt de operatie en kent het vluchtplan.', 'personal_info': 'De kluis opent om 22:15 met een code in drie delen.', 'clues': ['De bewaker wisselt om 21:50 van route.', 'Een insider heeft een valse badge.'], 'instructions': 'Houd het vluchtplan compact en let op wie het risico onnodig groter maakt.'},
            {'name': 'Double Agent', 'description': 'Jij werkt binnen de bank en hebt toegang tot het beveiligingssysteem.', 'personal_info': 'Camera 4 heeft een blinde hoek van 90 seconden.', 'clues': ['De achteringang wordt niet op video opgeslagen.', 'De alarmcode bevat de geboortedag van de manager.'], 'instructions': 'Geef bruikbare toegangsinformatie, maar maak je positie niet openbaar.'},
            {'name': 'Banker', 'description': 'Jij kent de geldstromen en kunt echte biljetten van lokgeld onderscheiden.', 'personal_info': 'De blauwe koffer bevat de echte buit.', 'clues': ['De blauwe koffer heeft een beschadigd slot.', 'De kluisvloer heeft een drukgevoelige tegel.'], 'instructions': 'Bescherm jouw kennis over de buit totdat het team een plan heeft.'},
            {'name': 'Operative', 'description': 'Jij voert de risicovolle acties uit en kent het terrein.', 'personal_info': 'Er is een onderhoudstunnel achter de lift.', 'clues': ['De lift wordt op afstand gevolgd.', 'In de tunnel ligt een reservejas.'], 'instructions': 'Blijf praktisch, maar vertel niet meteen welke uitgang jij wilt gebruiken.'},
        ],
        'theme': {'primary': '#1d4ed8', 'accent': '#f59e0b'},
    },
    'the_investigation': {
        'id': 'the_investigation', 'name': 'The Investigation', 'type': 'Onderzoek',
        'description': 'Leg getuigenissen, documenten en motieven naast elkaar tot het verhaal klopt.',
        'goal': 'Bouw een betrouwbare tijdlijn en wijs de Suspect aan.',
        'rules': ['Bronvermeldingen maken informatie sterker.', 'Een Witness mag details vergeten, maar niet bewust vervormen.', 'De Archivist beheert de documenten.'],
        'steps': ['Ontvang dossiers', 'Maak een tijdlijn', 'Vergelijk getuigenissen', 'Presenteer de conclusie'],
        'roles': [
            {'name': 'Detective', 'description': 'Je leidt het onderzoek en test elke theorie.', 'personal_info': 'Je hebt een ontbrekend dossier gevonden.', 'clues': ['De tijdlijn heeft een gat van twaalf minuten.', 'Een handtekening is nagemaakt.'], 'instructions': 'Stel gerichte vragen en leg vast welke bron elke conclusie ondersteunt.'},
            {'name': 'Witness', 'description': 'Jij zag een cruciaal moment, maar niet alles was duidelijk.', 'personal_info': 'Je hoorde een metalen klik vlak voor het licht uitging.', 'clues': ['De stem kwam uit de westelijke gang.', 'De geur van dennenhout bleef hangen.'], 'instructions': 'Maak onderscheid tussen wat je zag, hoorde en denkt te hebben gezien.'},
            {'name': 'Archivist', 'description': 'Jij bewaart documenten en herkent wijzigingen in oude dossiers.', 'personal_info': 'Een pagina is recent uit dossier 12 vervangen.', 'clues': ['De inkt op pagina 4 is nieuwer.', 'Het zegel staat ondersteboven.'], 'instructions': 'Laat documenten gecontroleerd rondgaan en vermeld ontbrekende stukken.'},
            {'name': 'Suspect', 'description': 'Jouw motief lijkt sterk, maar het volledige verhaal is ingewikkelder.', 'personal_info': 'Je was op de locatie, maar verliet die vóór het incident.', 'clues': ['Je hebt een geldig alibi voor het laatste kwartier.', 'Iemand anders gebruikte jouw pen.'], 'instructions': 'Verdedig jezelf met controleerbare feiten en onthul je motief pas wanneer nodig.'},
        ],
        'theme': {'primary': '#0f766e', 'accent': '#fbbf24'},
    },
}
VALID_STATUSES = {'draft', 'registration_open', 'registration_closed', 'started', 'finished'}


def config_for(preset_id: str) -> dict[str, Any]:
    config = GAME_CONFIGS.get(preset_id)
    if not config:
        raise HTTPException(status_code=400, detail='Onbekende game.')
    return config


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {**config, 'roles': [{'name': role['name'], 'description': role['description']} for role in config['roles']]}


async def admin_check(request: Request):
    if not settings.admin_password or request.headers.get('x-admin-password', '') != settings.admin_password:
        raise HTTPException(status_code=401, detail='Admin-authenticatie mislukt.')


async def state_row(conn):
    row = await conn.fetchrow('SELECT id, game_name, game_preset, registration_open, voting_active, status, theme, duration, active_generation_id, updated_at FROM game_state ORDER BY id LIMIT 1')
    if not row:
        raise HTTPException(status_code=503, detail='Spelstatus ontbreekt in de database.')
    return dict(row)


async def poll_payload(conn, include_results=False):
    poll = await conn.fetchrow('SELECT id, question, active FROM polls ORDER BY id LIMIT 1')
    if not poll:
        return {'active': False, 'question': '', 'options': []}
    options = await conn.fetch('SELECT id, label FROM poll_options WHERE poll_id=$1 ORDER BY sort_order, id', poll['id'])
    payload = {'active': poll['active'], 'question': poll['question'], 'options': [dict(option) for option in options]}
    if include_results:
        rows = await conn.fetch('SELECT o.id, o.label, count(v.id)::int AS votes FROM poll_options o LEFT JOIN poll_votes v ON v.option_id=o.id WHERE o.poll_id=$1 GROUP BY o.id ORDER BY o.sort_order, o.id', poll['id'])
        payload['results'] = [dict(row) for row in rows]
        payload['total'] = sum(row['votes'] for row in rows)
    return payload


@router.get('/health')
async def health():
    return {'status': 'ok', 'app': settings.app_name}


@router.get('/game-config')
async def game_config():
    return {'game_name': settings.app_name, 'games': [public_config(config) for config in GAME_CONFIGS.values()]}


@router.get('/game-state')
async def game_state():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await state_row(conn)
            return {'state': state, 'game': public_config(config_for(state['game_preset'])), 'poll': await poll_payload(conn)}
    finally:
        await pool.close()


@router.post('/join')
async def join(payload: JoinIn):
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail='Vul een geldige naam in.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await conn.fetchrow('SELECT registration_open, game_preset FROM game_state ORDER BY id LIMIT 1')
            if not state or not state['registration_open']:
                return JSONResponse(status_code=400, content={'success': False, 'message': 'Deelnemersregistratie is gesloten.'})
            try:
                await conn.execute('INSERT INTO players(name, email, access_token, game_preset, status) VALUES($1, $2, $3, $4, $5)', name, str(payload.email).lower(), str(uuid.uuid4()), state['game_preset'], 'registered')
            except asyncpg.UniqueViolationError:
                return JSONResponse(status_code=409, content={'success': False, 'message': 'Deze email is al aangemeld.'})
    finally:
        await pool.close()
    return {'success': True, 'message': 'Je bent aangemeld. Houd je inbox in de gaten.'}


@router.post('/game/select')
async def select_game(payload: GameSelectIn, request: Request):
    await admin_check(request)
    config = config_for(payload.game_preset)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('UPDATE game_state SET game_preset=$1, game_name=$2, theme=$3, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', config['id'], config['name'], json.dumps(config['theme']))
            return await state_row(conn)
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
            await conn.execute('UPDATE game_state SET status=$1, registration_open=$2, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', payload.status, payload.status == 'registration_open')
            return await state_row(conn)
    finally:
        await pool.close()


@router.post('/admin/registration')
async def registration(payload: ToggleIn, request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('UPDATE game_state SET registration_open=$1, status=$2, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', payload.active, 'registration_open' if payload.active else 'registration_closed')
            return await state_row(conn)
    finally:
        await pool.close()


@router.post('/admin/duration')
async def set_duration(payload: DurationIn, request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('UPDATE game_state SET duration=$1, updated_at=now() WHERE id=(SELECT id FROM game_state ORDER BY id LIMIT 1)', payload.duration)
            return await state_row(conn)
    finally:
        await pool.close()


@router.get('/poll')
async def get_poll():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return await poll_payload(conn)
    finally:
        await pool.close()


@router.post('/poll')
@router.post('/admin/poll')
async def configure_poll(payload: PollIn, request: Request):
    await admin_check(request)
    options = [option.strip() for option in payload.options if option.strip()]
    if len(options) < 2 or len(set(options)) != len(options):
        raise HTTPException(status_code=400, detail='Voeg minstens twee unieke opties toe.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            poll_id = await conn.fetchval('SELECT id FROM polls ORDER BY id LIMIT 1')
            await conn.execute('UPDATE polls SET question=$1, active=FALSE, updated_at=now() WHERE id=$2', payload.question.strip(), poll_id)
            await conn.execute('DELETE FROM poll_options WHERE poll_id=$1', poll_id)
            await conn.executemany('INSERT INTO poll_options(poll_id, label, sort_order) VALUES($1, $2, $3)', [(poll_id, option, index) for index, option in enumerate(options)])
            return await poll_payload(conn, include_results=True)
    finally:
        await pool.close()


@router.post('/poll/toggle')
async def toggle_poll(payload: ToggleIn, request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            poll_id = await conn.fetchval('SELECT id FROM polls ORDER BY id LIMIT 1')
            await conn.execute('UPDATE polls SET active=$1, updated_at=now() WHERE id=$2', payload.active, poll_id)
            return await poll_payload(conn, include_results=True)
    finally:
        await pool.close()


@router.post('/poll/vote')
async def vote(payload: VoteIn, request: Request):
    token = request.headers.get('x-vote-token') or (request.client.host if request.client else '')
    if not token:
        raise HTTPException(status_code=400, detail='Stemtoken ontbreekt.')
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            poll = await conn.fetchrow('SELECT id, active FROM polls ORDER BY id LIMIT 1')
            valid_option = await conn.fetchval('SELECT 1 FROM poll_options WHERE id=$1 AND poll_id=$2', payload.option_id, poll['id'] if poll else 0)
            if not poll or not poll['active'] or not valid_option:
                raise HTTPException(status_code=400, detail='De poll is niet actief of deze optie bestaat niet.')
            try:
                await conn.execute('INSERT INTO poll_votes(poll_id, option_id, voter_hash) VALUES($1, $2, $3)', poll['id'], payload.option_id, hashlib.sha256(token.encode()).hexdigest())
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail='Je hebt al gestemd.')
    finally:
        await pool.close()
    return {'success': True, 'message': 'Stem ontvangen.'}


@router.get('/admin/poll/results')
@router.get('/poll/results')
async def poll_results(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return await poll_payload(conn, include_results=True)
    finally:
        await pool.close()


@router.get('/admin/players')
@router.get('/players')
async def list_players(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT id, name, email, status, game_preset, created_at FROM players ORDER BY created_at ASC')
            return {'players': [dict(row) for row in rows]}
    finally:
        await pool.close()


@router.get('/players/count')
async def players_count(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return {'count': await conn.fetchval('SELECT count(*)::int FROM players')}
    finally:
        await pool.close()


def generated_player_payload(player: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    return {'id': player['player_id'], 'name': player['name'], 'email': player['email'], 'role': player['role'], 'role_description': player['role_description'], 'secret_information': player['secret_information'], 'clues': player['clues'], 'relationships': player.get('relationships', []), 'instructions': player['instructions']}


def email_role(player: dict[str, Any]) -> dict[str, Any]:
    return {'name': player['role'], 'description': player['role_description'], 'personal_info': player['secret_information'], 'objective': player.get('objective', ''), 'clues': player['clues'], 'instructions': player['instructions']}


async def active_generation(conn):
    state = await conn.fetchrow('SELECT active_generation_id FROM game_state ORDER BY id LIMIT 1')
    if not state or not state['active_generation_id']:
        raise HTTPException(status_code=404, detail='Er is nog geen actief gegenereerd spel.')
    generation = await conn.fetchrow('SELECT id, payload, created_at FROM generated_games WHERE id=$1', state['active_generation_id'])
    if not generation:
        raise HTTPException(status_code=404, detail='Actieve spelgeneratie ontbreekt.')
    return generation


async def player_for_token(conn, request: Request):
    token = request.headers.get('x-player-token') or request.query_params.get('token')
    if not token:
        raise HTTPException(status_code=401, detail='Player-token ontbreekt.')
    player = await conn.fetchrow('SELECT id, name, email FROM players WHERE access_token=$1 AND status=$2', token, 'assigned')
    if not player:
        raise HTTPException(status_code=401, detail='Ongeldig player-token.')
    return player


def release_at(created_at: datetime, days: int) -> datetime:
    return created_at + timedelta(days=days)


@router.get('/game/progression')
async def game_progression(request: Request):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            generation = await active_generation(conn)
            player = None
            try:
                player = await player_for_token(conn, request)
            except HTTPException:
                pass
            now = datetime.now(timezone.utc)
            phases = await conn.fetch('SELECT phase_number, name, purpose, open_question, release_after_days FROM game_phases WHERE generated_game_id=$1 ORDER BY phase_number', generation['id'])
            events = await conn.fetch('SELECT id, phase_number, title, description, delivery, release_after_days, player_ids FROM game_events WHERE generated_game_id=$1 ORDER BY phase_number, id', generation['id'])
            moments = await conn.fetch('SELECT id, phase_number, question, release_after_days, duration_hours, opened_at, closed_at FROM voting_moments WHERE generated_game_id=$1 ORDER BY phase_number, id', generation['id'])
            visible_phases = [dict(phase) for phase in phases if release_at(generation['created_at'], phase['release_after_days']) <= now]
            current_phase = max((phase['phase_number'] for phase in visible_phases), default=1)
            visible_events = []
            for event in events:
                allowed_players = event['player_ids'] or []
                if release_at(generation['created_at'], event['release_after_days']) <= now and (not allowed_players or not player or str(player['id']) in allowed_players):
                    visible_events.append(dict(event))
            voting = []
            for moment in moments:
                opened = release_at(generation['created_at'], moment['release_after_days'])
                closed = opened + timedelta(hours=moment['duration_hours'])
                voting.append({'id': moment['id'], 'phase_number': moment['phase_number'], 'question': moment['question'], 'open': opened <= now < closed, 'opened_at': opened, 'closed_at': closed})
            result = {'generation_id': str(generation['id']), 'current_phase': current_phase, 'phases': visible_phases, 'events': visible_events, 'voting_moments': voting}
            if player:
                assignment = await conn.fetchrow("SELECT payload FROM generated_player_data WHERE generated_game_id=$1 AND payload->>'database_player_id'=$2", generation['id'], str(player['id']))
                result['player'] = assignment['payload'] if assignment else None
                result['players'] = [dict(row) for row in await conn.fetch('SELECT id, name FROM players WHERE status=$1 ORDER BY id', 'assigned')]
            return result
    finally:
        await pool.close()


@router.post('/game/vote')
async def suspicion_vote(payload: SuspicionVoteIn, request: Request):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            player = await player_for_token(conn, request)
            generation = await active_generation(conn)
            if payload.candidate_player_id == player['id']:
                raise HTTPException(status_code=400, detail='Je kunt jezelf niet verdenken.')
            candidate = await conn.fetchval('SELECT 1 FROM players WHERE id=$1 AND status=$2', payload.candidate_player_id, 'assigned')
            if not candidate:
                raise HTTPException(status_code=400, detail='Ongeldige verdachte.')
            now = datetime.now(timezone.utc)
            moments = await conn.fetch('SELECT id, release_after_days, duration_hours FROM voting_moments WHERE generated_game_id=$1', generation['id'])
            active = next((moment for moment in moments if release_at(generation['created_at'], moment['release_after_days']) <= now < release_at(generation['created_at'], moment['release_after_days']) + timedelta(hours=moment['duration_hours'])), None)
            if not active:
                raise HTTPException(status_code=400, detail='Er is momenteel geen stemmoment geopend.')
            try:
                await conn.execute('INSERT INTO suspicion_votes(voting_moment_id, generated_game_id, voter_player_id, candidate_player_id) VALUES($1, $2, $3, $4)', active['id'], generation['id'], player['id'], payload.candidate_player_id)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(status_code=409, detail='Je hebt voor dit stemmoment al gestemd.') from exc
            return {'success': True, 'message': 'Je geheime verdenking is opgeslagen.'}
    finally:
        await pool.close()


async def evaluate_objectives(conn, generation_id):
    assignments = [row['payload'] for row in await conn.fetch('SELECT payload FROM generated_player_data WHERE generated_game_id=$1 ORDER BY id', generation_id)]
    votes = await conn.fetch('SELECT voting_moment_id, voter_player_id, candidate_player_id FROM suspicion_votes WHERE generated_game_id=$1', generation_id)
    counts: dict[int, int] = {}
    for vote in votes:
        counts[vote['candidate_player_id']] = counts.get(vote['candidate_player_id'], 0) + 1
    maximum = max(counts.values(), default=0)
    outcomes = []
    for assignment in assignments:
        database_id = assignment.get('database_player_id')
        if not database_id:
            continue
        for objective in assignment.get('personal_objectives', []):
            target_id = objective.get('target_player_id')
            target_database_id = next((item.get('database_player_id') for item in assignments if item.get('player_id') == target_id), None)
            metric = objective.get('metric')
            if metric == 'vote_received':
                achieved = counts.get(int(target_database_id or 0), 0) >= int(objective.get('target_value') or 1)
            elif metric == 'top_suspect':
                achieved = bool(target_database_id) and counts.get(int(target_database_id), 0) == maximum and maximum > 0
            elif metric == 'not_top_suspect':
                achieved = counts.get(int(database_id), 0) < maximum
            elif metric == 'mutual_suspicion':
                achieved = any(vote['voter_player_id'] == int(database_id) and vote['candidate_player_id'] == int(target_database_id or 0) for vote in votes) and any(vote['voter_player_id'] == int(target_database_id or 0) and vote['candidate_player_id'] == int(database_id) for vote in votes)
            elif metric == 'vote_change':
                own_votes = [vote['candidate_player_id'] for vote in votes if vote['voter_player_id'] == int(database_id)]
                achieved = len(own_votes) >= 2 and own_votes[0] != own_votes[-1]
            else:
                achieved = False
            status = 'achieved' if achieved else 'failed'
            await conn.execute('INSERT INTO objective_status(generated_game_id, player_id, objective_id, status, evaluated_at) VALUES($1, $2, $3, $4, now()) ON CONFLICT (generated_game_id, player_id, objective_id) DO UPDATE SET status=EXCLUDED.status, evaluated_at=EXCLUDED.evaluated_at', generation_id, int(database_id), objective['id'], status)
            outcomes.append({'player_id': assignment['player_id'], 'objective_id': objective['id'], 'text': objective['text'], 'status': status})
    return outcomes


async def finale_payload(conn, generation, include_secret: bool):
    payload = generation['payload']
    outcomes = await evaluate_objectives(conn, generation['id'])
    vote_rows = await conn.fetch('SELECT voting_moment_id, voter_player_id, candidate_player_id FROM suspicion_votes WHERE generated_game_id=$1 ORDER BY voting_moment_id, created_at', generation['id'])
    players = {row['id']: row['name'] for row in await conn.fetch('SELECT id, name FROM players')}
    history = {}
    for vote in vote_rows:
        history.setdefault(vote['voting_moment_id'], []).append({'voter': players.get(vote['voter_player_id']), 'candidate': players.get(vote['candidate_player_id'])})
    result = {'title': payload['title'], 'story': payload['story'], 'voting_history': history, 'objective_results': outcomes}
    if include_secret:
        result.update({'solution': payload['solution'], 'truth_model': payload['truth_model'], 'saboteur_count': payload['saboteur_count'], 'team_win_condition': payload['team_win_condition'], 'saboteur_win_condition': payload['saboteur_win_condition']})
    return result


@router.get('/admin/finale')
async def admin_finale(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            generation = await active_generation(conn)
            return await finale_payload(conn, generation, True)
    finally:
        await pool.close()


@router.get('/game/finale')
async def player_finale(request: Request):
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await conn.fetchrow('SELECT status FROM game_state ORDER BY id LIMIT 1')
            if not state or state['status'] != 'finished':
                raise HTTPException(status_code=403, detail='De finale is nog niet vrijgegeven.')
            player = await player_for_token(conn, request)
            generation = await active_generation(conn)
            result = await finale_payload(conn, generation, True)
            assignment = await conn.fetchrow("SELECT payload FROM generated_player_data WHERE generated_game_id=$1 AND payload->>'database_player_id'=$2", generation['id'], str(player['id']))
            generated_player_id = assignment['payload'].get('player_id') if assignment else None
            result['my_objectives'] = [item for item in result['objective_results'] if item['player_id'] == generated_player_id]
            return result
    finally:
        await pool.close()


async def generate_and_store(conn, game: dict[str, Any], names: list[str], mode: str, request: GenerateIn) -> tuple[str, GeneratedGame, list[dict[str, Any]]]:
    try:
        generated = await ai_service.generate_game(game=game, names=names, difficulty=request.difficulty, duration=request.duration, clue_count=request.clue_count)
    except AIProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail={'code': exc.code, 'message': str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={'code': 'AI_GAME_GENERATION_FAILED', 'message': str(exc)}) from exc
    if len(generated.players) != len(names):
        raise HTTPException(status_code=502, detail={'code': 'AI_GAME_GENERATION_FAILED', 'message': 'De AI leverde niet voor iedere speler speldata.'})
    generation_id = uuid.uuid4()
    payload = generated.model_dump() if hasattr(generated, 'model_dump') else generated.dict()
    await conn.execute('INSERT INTO generated_games(id, game_preset, mode, difficulty, duration, payload) VALUES($1, $2, $3, $4, $5, $6)', generation_id, game['id'], mode, generated.difficulty, generated.duration, json.dumps(payload))
    await conn.executemany('INSERT INTO game_phases(generated_game_id, phase_number, name, purpose, open_question, release_after_days, objectives) VALUES($1, $2, $3, $4, $5, $6, $7)', [(generation_id, phase.number, phase.name, phase.purpose, phase.open_question, phase.release_after_days, json.dumps(phase.objectives)) for phase in generated.phases])
    await conn.executemany('INSERT INTO game_events(id, generated_game_id, phase_number, title, description, delivery, release_after_days, player_ids) VALUES($1, $2, $3, $4, $5, $6, $7, $8)', [(event.id, generation_id, event.phase, event.title, event.description, event.delivery, event.release_after_days, json.dumps(event.player_ids)) for event in generated.events])
    await conn.executemany('INSERT INTO voting_moments(id, generated_game_id, phase_number, question, release_after_days, duration_hours) VALUES($1, $2, $3, $4, $5, $6)', [(moment.id, generation_id, moment.phase, moment.question, moment.release_after_days, moment.duration_hours) for moment in generated.voting_moments])
    output = []
    for index, generated_player in enumerate(generated.players):
        player = generated_player.model_dump() if hasattr(generated_player, 'model_dump') else generated_player.dict()
        player['name'] = names[index]
        player['email'] = f'test-speler-{index + 1}@example.com' if mode == 'test' else ''
        await conn.execute('INSERT INTO generated_player_data(generated_game_id, player_id, payload) VALUES($1, $2, $3)', generation_id, player['player_id'], json.dumps(player))
        output.append(player)
    return str(generation_id), generated, output


@router.get('/admin/test')
async def test_info(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await state_row(conn)
            row = await conn.fetchrow('SELECT payload FROM generated_games WHERE mode=$1 ORDER BY created_at DESC LIMIT 1', 'test')
            generated = row['payload'] if row else None
            if generated:
                generated['players'] = [item['payload'] for item in await conn.fetch('SELECT payload FROM generated_player_data WHERE generated_game_id=(SELECT id FROM generated_games WHERE mode=$1 ORDER BY created_at DESC LIMIT 1) ORDER BY id', 'test')]
            return {'game': public_config(config_for(state['game_preset'])), 'generated_game': generated}
    finally:
        await pool.close()


@router.post('/admin/test/simulate')
async def simulate(payload: GenerateIn, request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await state_row(conn)
            game = config_for(state['game_preset'])
            names = [f'Test Speler {index}' for index in range(1, payload.player_count + 1)]
            generation_id, generated, players = await generate_and_store(conn, game, names, 'test', payload)
            return {'generation_id': generation_id, 'game': generated.model_dump() if hasattr(generated, 'model_dump') else generated.dict(), 'players': players}
    finally:
        await pool.close()


@router.get('/admin/test/emails')
async def test_emails(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id, game_preset, payload FROM generated_games WHERE mode=$1 ORDER BY created_at DESC LIMIT 1', 'test')
            if not row:
                raise HTTPException(status_code=400, detail='Genereer eerst een testspel.')
            generated = row['payload']
            game = config_for(row['game_preset'])
            players = [item['payload'] for item in await conn.fetch('SELECT payload FROM generated_player_data WHERE generated_game_id=$1 ORDER BY id', row['id'])]
            emails = [build_secret_email(player_name=player.get('name', f'Test Speler {index + 1}'), to_email=player.get('email', f'test-speler-{index + 1}@example.com'), game={'name': generated['game_name']}, role=email_role(player)) for index, player in enumerate(players)]
            return {'emails': emails, 'generation_id': str(row['id'])}
    finally:
        await pool.close()


@router.post('/admin/start-game')
async def start_game(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            state = await state_row(conn)
            game = config_for(state['game_preset'])
            players = [dict(player) for player in await conn.fetch('SELECT id, name, email, access_token FROM players ORDER BY created_at ASC')]
            if not players:
                raise HTTPException(status_code=400, detail='Voeg eerst deelnemers toe voordat je het spel start.')
            for player in players:
                if not player['access_token']:
                    player['access_token'] = str(uuid.uuid4())
                    await conn.execute('UPDATE players SET access_token=$1 WHERE id=$2', player['access_token'], player['id'])
            state_duration = state.get('duration') or 'avond'
            generation_request = GenerateIn(player_count=len(players), duration=state_duration)
            _, generated, assignments = await generate_and_store(conn, game, [player['name'] for player in players], 'live', generation_request)
            for player, assignment in zip(players, assignments):
                await conn.execute('UPDATE players SET role=$1, personal_info=$2, secret_info=$3, clues=$4, status=$5, updated_at=now() WHERE id=$6', assignment['role'], assignment['role_description'], assignment['secret_information'], json.dumps(assignment['clues']), 'assigned', player['id'])
            generation_id = await conn.fetchval('SELECT id FROM generated_games WHERE mode=$1 ORDER BY created_at DESC LIMIT 1', 'live')
            for player, assignment in zip(players, assignments):
                await conn.execute("UPDATE generated_player_data SET payload=jsonb_set(payload, '{database_player_id}', to_jsonb($1::text)) WHERE generated_game_id=$2 AND player_id=$3", str(player['id']), generation_id, assignment['player_id'])
            await conn.execute("UPDATE game_state SET status='started', registration_open=FALSE, duration=$1, active_generation_id=$2, updated_at=now() WHERE id=$3", generated.duration, generation_id, state['id'])
            assigned = await conn.fetch('SELECT id, name, email, role, access_token FROM players ORDER BY id')
        email_errors = []
        for player, assignment in zip(assigned, assignments):
            try:
                role = email_role(assignment)
                role['player_token'] = player['access_token']
                await send_secret_email(player['email'], player_name=player['name'], game={'name': generated.game_name}, role=role)
            except Exception as exc:
                logger.exception('Secret email failed for player %s', player['id'])
                email_errors.append(str(exc))
        return {'success': True, 'state': await get_state_after_start(), 'email_errors': email_errors}
    finally:
        await pool.close()


async def get_state_after_start():
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            return await state_row(conn)
    finally:
        await pool.close()


@router.post('/reset')
async def reset(request: Request):
    await admin_check(request)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute('TRUNCATE players')
            await conn.execute("UPDATE game_state SET status='draft', registration_open=TRUE, active_generation_id=NULL, duration='avond', updated_at=now()")
        return {'success': True, 'message': 'Alle deelnemers verwijderd.'}
    finally:
        await pool.close()
