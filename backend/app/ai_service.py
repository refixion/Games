import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings

logger = logging.getLogger(__name__)


class AIProviderUnavailable(RuntimeError):
    code = 'AI_PROVIDER_NOT_CONFIGURED'


class GeneratedPlayer(BaseModel):
    player_id: str
    role: str
    role_description: str
    secret_information: str
    clues: list[str] = Field(min_length=2)
    relationships: list[str] = Field(default_factory=list)
    instructions: str


class GeneratedGame(BaseModel):
    game: str
    story: str
    objective: str
    rules: list[str] = Field(min_length=1)
    players: list[GeneratedPlayer] = Field(min_length=1)
    solution: str
    difficulty: str


class AIService:
    async def generate_game(self, *, game: dict[str, Any], names: list[str], difficulty: str = 'medium', clue_count: int = 3) -> GeneratedGame:
        if not settings.ai_api_key:
            raise AIProviderUnavailable('AI_PROVIDER_NOT_CONFIGURED: configureer AI_API_KEY voor echte gamegeneratie.')
        prompt = {
            'game': game['name'], 'game_rules': game['rules'], 'available_roles': [role['name'] for role in game['roles']],
            'players': [{'player_id': str(index + 1), 'name': name} for index, name in enumerate(names)],
            'theme': game.get('theme', {}), 'objective': game['goal'], 'difficulty': difficulty, 'clue_count': clue_count,
            'requirements': ['Maak een oplosbaar, samenhangend verhaal.', 'Geef iedere speler unieke informatie.', 'Laat clues tussen spelers naar hetzelfde bewijs of dezelfde gebeurtenis verwijzen.', 'Gebruik rollen meerdere keren alleen als dat narratief logisch is en geef iedere speler een unieke rolvariant.', 'Geef uitsluitend geldig JSON terug volgens het gevraagde schema.'],
        }
        schema = GeneratedGame.model_json_schema() if hasattr(GeneratedGame, 'model_json_schema') else GeneratedGame.schema()
        body = {'model': settings.ai_model, 'temperature': 0.2, 'messages': [{'role': 'system', 'content': 'Je bent een professionele tabletop game designer. Antwoord uitsluitend met JSON.'}, {'role': 'user', 'content': json.dumps({'request': prompt, 'schema': schema}, ensure_ascii=False)}], 'response_format': {'type': 'json_object'}}
        headers = {'Authorization': f'Bearer {settings.ai_api_key}', 'Content-Type': 'application/json'}
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(f'{settings.ai_base_url.rstrip("/")}/chat/completions', json=body, headers=headers)
                response.raise_for_status()
                content = response.json()['choices'][0]['message']['content']
                raw = json.loads(content)
                return GeneratedGame.model_validate(raw) if hasattr(GeneratedGame, 'model_validate') else GeneratedGame.parse_obj(raw)
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
            logger.exception('AI game generation failed')
            raise RuntimeError(f'AI_GAME_GENERATION_FAILED: {exc}') from exc


ai_service = AIService()
