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


class GeneratedPlayer(BaseModel):
    class Config:
        extra = 'forbid'

    player_id: str
    name: str
    role: str
    role_description: str
    objective: str
    secret_information: str
    clues: list[str] = Field(min_length=2)
    relationships: list[str]
    instructions: str


class GeneratedGame(BaseModel):
    class Config:
        extra = 'forbid'

    game: str
    title: str
    story: str
    objective: str
    rules: list[str] = Field(min_length=1)
    players: list[GeneratedPlayer] = Field(min_length=1)
    solution: str
    difficulty: Literal['easy', 'medium', 'hard']


class AIService:
    async def generate_game(self, *, game: dict[str, Any], names: list[str], difficulty: str = 'medium', clue_count: int = 3) -> GeneratedGame:
        if not settings.ai_api_key:
            raise AIProviderUnavailable('AI_PROVIDER_NOT_CONFIGURED: configureer AI_API_KEY voor echte gamegeneratie.')
        prompt = {
            'game': game['name'], 'game_rules': game['rules'], 'available_roles': [role['name'] for role in game['roles']],
            'players': [{'player_id': str(index + 1), 'name': name} for index, name in enumerate(names)],
            'theme': game.get('theme', {}), 'objective': game['goal'], 'difficulty': difficulty, 'clue_count': clue_count,
            'requirements': [
                'Return ONLY the requested structured game object.',
                'The output MUST contain game, title, story, objective, rules, difficulty, solution, and players.',
                'difficulty MUST be exactly easy, medium, or hard.',
                'solution is the secret canonical solution and must never be shown to normal players.',
                'Every player MUST contain player_id, name, role, role_description, objective, secret_information, clues, relationships, and instructions.',
                'Generate exactly one player for every requested name, with one non-empty role and at least the requested number of unique clues per player.',
                'Make the clues distinct across players, connect them through relationships, and ensure the solution can be deduced from the clues.',
            ],
        }
        schema = GeneratedGame.model_json_schema() if hasattr(GeneratedGame, 'model_json_schema') else GeneratedGame.schema()
        schema = _strict_schema(schema)
        body = {
            'model': settings.ai_model,
            'temperature': 0.2,
            'messages': [
                {'role': 'system', 'content': 'You are a professional tabletop game designer. Return ONLY the requested structured game object. The generated game MUST contain game, title, story, objective, rules, difficulty, solution, and players. solution and difficulty are mandatory. difficulty must be exactly easy, medium, or hard. solution is the secret canonical solution and must never be shown to normal players.'},
                {'role': 'user', 'content': json.dumps({'request': prompt, 'output_requirements': {'required_fields': ['game', 'title', 'story', 'objective', 'rules', 'difficulty', 'solution', 'players'], 'player_required_fields': ['player_id', 'name', 'role', 'role_description', 'objective', 'secret_information', 'clues', 'relationships', 'instructions'], 'difficulty': ['easy', 'medium', 'hard']}}, ensure_ascii=False)},
            ],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'generated_game', 'strict': True, 'schema': schema}},
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
                    _validate_generation(generated, game, names, clue_count, difficulty)
                    return generated
            except ValidationError as exc:
                logger.error('AI generation validation failed on attempt %s: %s', attempt, exc.errors())
                last_error = exc
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
    for definition in schema.get('$defs', {}).values():
        _strict_schema(definition)
    return schema


def _validate_generation(generated: GeneratedGame, game: dict[str, Any], names: list[str], clue_count: int, requested_difficulty: str) -> None:
    if generated.game != game['id']:
        raise ValueError(f'generated game does not match selected game: {generated.game}')
    if len(generated.players) != len(names):
        raise ValueError(f'expected {len(names)} players, received {len(generated.players)}')
    if not generated.solution.strip() or not generated.difficulty:
        raise ValueError('solution and difficulty are required')
    if generated.difficulty != requested_difficulty:
        raise ValueError(f'expected difficulty {requested_difficulty}, received {generated.difficulty}')
    player_ids = [player.player_id for player in generated.players]
    if len(set(player_ids)) != len(player_ids):
        raise ValueError('player_id values must be unique')
    all_clues = [clue.strip() for player in generated.players for clue in player.clues]
    if any(not clue for clue in all_clues) or len(set(all_clues)) != len(all_clues):
        raise ValueError('clues must be non-empty and unique across players')
    for index, player in enumerate(generated.players):
        if player.name != names[index] or len(player.clues) < max(2, clue_count):
            raise ValueError(f'player {index + 1} has invalid name or insufficient clues')
        if not player.role.strip():
            raise ValueError(f'player {index + 1} has no role')


ai_service = AIService()
