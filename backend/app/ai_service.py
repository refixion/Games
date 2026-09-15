import json
import logging
import asyncio
from typing import Any
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings

logger = logging.getLogger(__name__)


class AIProviderUnavailable(RuntimeError):
    code = 'AI_PROVIDER_NOT_CONFIGURED'


Duration = Literal['avond', '1_week', '2_weken', '3_weken', '1_maand']


class GeneratedClue(BaseModel):
    id: str
    text: str
    clue_type: Literal['direct', 'indirect', 'relational', 'timeline', 'alibi', 'location', 'object', 'witness', 'confirming', 'crucial', 'red_herring', 'personal']
    owner_player_id: str
    release_phase: int = Field(ge=1)
    visibility: Literal['public', 'private', 'shareable']
    supports: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    red_herring: bool = False


class GeneratedObjective(BaseModel):
    id: str
    text: str
    owner_player_id: str
    measurable: bool
    metric: Literal['vote_received', 'top_suspect', 'not_top_suspect', 'mutual_suspicion', 'theory_adopted', 'vote_change', 'clue_found', 'manual_review']
    target_player_id: str | None = None
    target_value: int | None = None
    activate_phase: int = Field(ge=1)


class GeneratedPlayer(BaseModel):
    class Config:
        extra = 'forbid'

    player_id: str
    name: str
    role: str
    role_description: str
    objective: str
    personal_objectives: list[GeneratedObjective] = Field(min_length=1)
    secret_information: str
    clues: list[str] = Field(min_length=2)
    relationships: list[str]
    instructions: str
    is_saboteur: bool = False


class GeneratedPhase(BaseModel):
    number: int = Field(ge=1)
    name: str
    purpose: str
    open_question: str
    release_after_days: int = Field(ge=0)
    objectives: list[str] = Field(min_length=1)


class GeneratedEvent(BaseModel):
    id: str
    phase: int = Field(ge=1)
    title: str
    description: str
    delivery: Literal['website', 'email', 'physical_clue', 'qr_code', 'whatsapp', 'printed_document']
    release_after_days: int = Field(ge=0)
    player_ids: list[str] = Field(min_length=1)


class GeneratedVotingMoment(BaseModel):
    id: str
    phase: int = Field(ge=1)
    question: str
    release_after_days: int = Field(ge=0)
    duration_hours: int = Field(ge=1, le=168)


class GeneratedGame(BaseModel):
    class Config:
        extra = 'forbid'

    game_id: Literal[
    'murder_mystery',
    'the_heist',
    'the_investigation'
    ]

    game_name: str
    title: str
    story: str
    objective: str
    rules: list[str] = Field(min_length=1)
    players: list[GeneratedPlayer] = Field(min_length=1)
    solution: str
    difficulty: Literal['easy', 'medium', 'hard']
    duration: Duration
    saboteur_count: int = Field(ge=1)
    team_win_condition: str
    individual_win_condition: str
    saboteur_win_condition: str
    truth_model: str
    phases: list[GeneratedPhase] = Field(min_length=1)
    events: list[GeneratedEvent] = Field(default_factory=list)
    voting_moments: list[GeneratedVotingMoment] = Field(min_length=1)
    clues: list[GeneratedClue] = Field(min_length=1)


class AIService:
    async def generate_game(self, *, game: dict[str, Any], names: list[str], difficulty: str = 'medium', duration: str = 'avond', clue_count: int = 3) -> GeneratedGame:
        if not settings.ai_api_key:
            raise AIProviderUnavailable('AI_PROVIDER_NOT_CONFIGURED: configureer AI_API_KEY voor echte gamegeneratie.')
        prompt = {
            'game_id': game['id'],
            'game_name': game['name'],
            'game_rules': game['rules'],
            'available_roles': [role['name'] for role in game['roles']],
            'players': [{'player_id': str(index + 1), 'name': name} for index, name in enumerate(names)],
            'theme': game.get('theme', {}),
            'objective': game['goal'],
            'difficulty': difficulty,
            'duration': duration,
            'clue_count': clue_count,
            'language': 'Nederlands voor alle player-facing content; role names exact uit de role pool en Engels.',
            'design_process': [
                'Maak eerst intern een canonical truth model met wie, wat, waar, wanneer en waarom.',
                'Plan daarna rolbalans, sabotage, phases, events, clue dependencies en voting moments.',
                'Schrijf daarna alle player-facing content vanuit dat model.',
                'Controleer dat de solution logisch volgt en lange durations echte progression, delayed information en minstens een twist hebben.',
            ],
            'duration_rules': {
                'avond': '1-2 voting moments, 1-4 uur, compacte finale en weinig delayed events.',
                '1_week': 'meerdere speelmomenten, minstens 1 vervolgverdenking en enkele events.',
                '2_weken': 'minstens 3 phases, 2 voting moments, verspreide clues, sociale interactie en een twist.',
                '3_weken': 'uitgebreide progression, meerdere releases, objectives en revelations.',
                '1_maand': 'campagnegevoel, minstens 5 phases, 3+ voting moments, events, mid-game twist en finale.',
            },
            'requirements': [
                'Return ONLY the requested structured game object.',
                'The output MUST contain game_id, game_name, title, story, objective, rules, difficulty, solution, and players.',
                'game_id is an immutable canonical identifier. Return exactly the provided game_id. Never translate, capitalize, rename, or modify it.',
                'game_name must be the provided human-readable game name.',
                'difficulty MUST be exactly easy, medium, or hard.',
                'solution is the secret canonical solution and must never be shown to normal players.',
                'Every player MUST contain player_id, name, role, role_description, objective, personal_objectives, secret_information, clues, relationships, instructions, and is_saboteur.',
                'Generate exactly one player for every requested name, with one role from available_roles, at least one personal objective, and relevant information.',
                'Generate phases, delayed events, voting moments, clue dependencies and a truth model. Keep all player-facing content in Dutch.',
            ],
        }

        body = {
            'model': settings.ai_model,
            'temperature': 0.2,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are a professional tabletop game designer. '
                    'Return ONLY the requested structured game object. '
                    'The generated game MUST contain game_id, game_name, title, story, '
                    'objective, rules, difficulty, solution, and players. '
                    'game_id is an immutable canonical identifier and MUST exactly match '
                    'the provided game_id. Never translate, capitalize, rename, or modify it. '
                    'solution and difficulty are mandatory. '
                    'difficulty must be exactly easy, medium, or hard. '
                    'solution and truth_model are secret canonical information and must never be shown to normal players. Include duration, phases, events, clues and voting_moments.'
                )
            },
            {
                'role': 'user',
                'content': json.dumps(
                    {
                        'request': prompt,
                        'output_requirements': {
                            'required_fields': [
                                'game_id',
                                'game_name',
                                'title',
                                'story',
                                'objective',
                                'rules',
                                'difficulty',
                                'solution',
                                'players'
                            ],
                            'player_required_fields': [
                                'player_id',
                                'name',
                                'role',
                                'role_description',
                                'objective',
                                'secret_information',
                                'clues',
                                'relationships',
                                'instructions'
                            ],
                            'difficulty': ['easy', 'medium', 'hard']
                        }
                    },
                    ensure_ascii=False
                )
            },
        ],
            'response_format': {'type': 'json_object'},
        }
        headers = {'Authorization': f'Bearer {settings.ai_api_key}', 'Content-Type': 'application/json'}
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=45) as client:
                    response = await client.post(f'{settings.ai_base_url.rstrip("/")}/chat/completions', json=body, headers=headers)
                    response.raise_for_status()
                    content = response.json()['choices'][0]['message']['content']
                    raw = json.loads(content)
                    generated = GeneratedGame.model_validate(raw) if hasattr(GeneratedGame, 'model_validate') else GeneratedGame.parse_obj(raw)
                    _validate_generation(generated, game, names, clue_count, difficulty, duration)
                    return generated
            except ValidationError as exc:
                logger.error('AI generation validation failed on attempt %s: %s', attempt, exc.errors())
                last_error = exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                logger.error(
                    'Groq API error %s: %s',
                    status,
                    exc.response.text[:4000],
                )

                last_error = exc

                if status not in {429, 500, 502, 503, 504}:
                    break

            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.exception('AI game generation request failed on attempt %s', attempt)
                last_error = exc
            if attempt < 3:
                await asyncio.sleep(0.5 * attempt)
        raise RuntimeError(f'AI_GAME_GENERATION_FAILED: {last_error}') from last_error


def _strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make Pydantic's schema acceptable to Groq strict structured outputs."""
    if not isinstance(schema, dict):
        return schema
    if schema.get('type') == 'object' or 'properties' in schema:
        schema['additionalProperties'] = False
        schema['required'] = list(schema.get('properties', {}).keys())
        for child in schema.get('properties', {}).values():
            _strict_schema(child)
    for key in ('items', 'additionalProperties'):
        child = schema.get(key)
        if isinstance(child, dict):
            _strict_schema(child)
    for key in ('anyOf', 'oneOf', 'allOf'):
        for child in schema.get(key, []):
            if isinstance(child, dict):
                _strict_schema(child)
    for definitions_key in ('$defs', 'definitions'):
        for definition in schema.get(definitions_key, {}).values():
            _strict_schema(definition)

    return schema


def _validate_generation(generated: GeneratedGame, game: dict[str, Any], names: list[str], clue_count: int, requested_difficulty: str, requested_duration: str) -> None:
    if generated.game_id != game['id'] or generated.game_name != game['name']:
        raise ValueError('canonical game_id and game_name must match selected game')
    if len(generated.players) != len(names):
        raise ValueError(f'expected {len(names)} players, received {len(generated.players)}')
    if not generated.solution.strip() or not generated.difficulty:
        raise ValueError('solution and difficulty are required')
    if generated.difficulty != requested_difficulty:
        raise ValueError(f'expected difficulty {requested_difficulty}, received {generated.difficulty}')
    if generated.duration != requested_duration:
        raise ValueError(f'expected duration {requested_duration}, received {generated.duration}')
    player_ids = {player.player_id for player in generated.players}
    if player_ids != {str(index + 1) for index in range(len(names))}:
        raise ValueError('player_id values must be unique and sequential')
    role_names = {role['name'] for role in game['roles']}
    if generated.saboteur_count != sum(player.is_saboteur for player in generated.players) or generated.saboteur_count < 1:
        raise ValueError('saboteur_count does not match player assignments')
    minimum_phases = 5 if requested_duration == '1_maand' else 3 if requested_duration in {'2_weken', '3_weken'} else 1
    minimum_votes = 3 if requested_duration == '1_maand' else 2 if requested_duration in {'2_weken', '3_weken'} else 1
    if len(generated.phases) < minimum_phases or len(generated.voting_moments) < minimum_votes:
        raise ValueError('duration requires meaningful phases and voting moments')
    clue_ids = [clue.id for clue in generated.clues]
    if len(clue_ids) != len(set(clue_ids)) or len(generated.clues) < len(names) * max(1, clue_count):
        raise ValueError('clues must be unique and sufficient for the player count')
    if any(clue.owner_player_id not in player_ids for clue in generated.clues):
        raise ValueError('clue owners must reference players')
    for index, player in enumerate(generated.players):
        if player.name != names[index] or player.role not in role_names or len(player.clues) < max(1, clue_count):
            raise ValueError(f'player {index + 1} has invalid name or insufficient clues')
        if not player.personal_objectives:
            raise ValueError(f'player {index + 1} has no personal objective')


ai_service = AIService()
