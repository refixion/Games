import asyncio
import json
import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import settings

logger = logging.getLogger(__name__)


class AIProviderUnavailable(RuntimeError):
    code = "AI_PROVIDER_NOT_CONFIGURED"


Duration = Literal["avond", "1_week", "2_weken", "3_weken", "1_maand"]


class GeneratedClue(BaseModel):
    id: str
    text: str
    clue_type: Literal[
        "direct",
        "indirect",
        "relational",
        "timeline",
        "alibi",
        "location",
        "object",
        "witness",
        "confirming",
        "crucial",
        "red_herring",
        "personal",
    ]
    owner_player_id: str
    release_phase: int = Field(ge=1)
    visibility: Literal["public", "private", "shareable"]
    supports: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    red_herring: bool = False


class GeneratedObjective(BaseModel):
    id: str
    text: str
    owner_player_id: str
    measurable: bool
    metric: Literal[
        "vote_received",
        "top_suspect",
        "not_top_suspect",
        "mutual_suspicion",
        "theory_adopted",
        "vote_change",
        "clue_found",
        "manual_review",
    ]
    target_player_id: str | None = None
    target_value: int | None = None
    activate_phase: int = Field(ge=1)


class GeneratedPlayer(BaseModel):
    class Config:
        extra = "forbid"

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
    delivery: Literal[
        "website",
        "email",
        "physical_clue",
        "qr_code",
        "whatsapp",
        "printed_document",
    ]
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
        extra = "forbid"

    game_id: Literal[
        "murder_mystery",
        "the_heist",
        "the_investigation",
    ]

    game_name: str
    title: str
    story: str
    objective: str
    rules: list[str] = Field(min_length=1)
    players: list[GeneratedPlayer] = Field(min_length=1)
    solution: str
    difficulty: Literal["easy", "medium", "hard"]
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
    async def generate_game(
        self,
        *,
        game: dict[str, Any],
        names: list[str],
        difficulty: str = "medium",
        duration: str = "avond",
        clue_count: int = 3,
    ) -> GeneratedGame:
        if not settings.ai_api_key:
            raise AIProviderUnavailable(
                "AI_PROVIDER_NOT_CONFIGURED: configureer AI_API_KEY voor echte gamegeneratie."
            )

        prompt = {
            "game_id": game["id"],
            "game_name": game["name"],
            "game_rules": game["rules"],
            "available_roles": [
                role["name"] for role in game["roles"]
            ],
            "players": [
                {
                    "player_id": str(index + 1),
                    "name": name,
                }
                for index, name in enumerate(names)
            ],
            "theme": game.get("theme", {}),
            "objective": game["goal"],
            "difficulty": difficulty,
            "duration": duration,
            "clue_count": clue_count,
            "language": (
                "Nederlands voor alle player-facing content; "
                "role names exact uit de role pool en Engels."
            ),
            "design_process": [
                "Maak eerst intern een canonical truth model met wie, wat, waar, wanneer en waarom.",
                "Plan daarna rolbalans, sabotage, phases, events, clue dependencies en voting moments.",
                "Schrijf daarna alle player-facing content vanuit dat model.",
                "Controleer daarna alle IDs, relaties, objectives, clues, fases, events en stemmomenten.",
                "Controleer dat de solution logisch volgt uit de clues.",
                "Bij lange durations moeten progression, delayed information en minstens één twist aanwezig zijn.",
            ],
            "duration_rules": {
                "avond": (
                    "1-2 voting moments, 1-4 uur, "
                    "compacte finale en weinig delayed events."
                ),
                "1_week": (
                    "meerdere speelmomenten, minstens 1 vervolgverdenking "
                    "en enkele events."
                ),
                "2_weken": (
                    "minstens 3 phases, 2 voting moments, verspreide clues, "
                    "sociale interactie en een twist."
                ),
                "3_weken": (
                    "uitgebreide progression, meerdere releases, "
                    "objectives en revelations."
                ),
                "1_maand": (
                    "campagnegevoel, minstens 5 phases, 3+ voting moments, "
                    "events, mid-game twist en finale."
                ),
            },
            "requirements": [
                "Return ONLY the requested structured JSON game object.",
                "Do not return markdown.",
                "Do not wrap the JSON in ```json fences.",
                "The output MUST contain every field listed in output_requirements.",
                "game_id is an immutable canonical identifier. "
                "Return exactly the provided game_id. "
                "Never translate, capitalize, rename, or modify it.",
                "game_name must be exactly the provided human-readable game name.",
                "difficulty MUST be exactly easy, medium, or hard.",
                "duration MUST be exactly the requested duration.",
                "solution is the secret canonical solution and must never be shown to normal players.",
                "truth_model is secret canonical information and must never be shown to normal players.",
                "Generate exactly one player for every requested name.",
                "Players MUST remain in exactly the same order as the requested players.",
                "Each player must have exactly one role from available_roles.",
                "personal_objectives MUST be a JSON array of objective objects matching the requested structure.",
                "Every personal objective owner_player_id MUST equal the player's player_id.",
                "relationships MUST be a JSON array of strings. Never use an object or dictionary.",
                "is_saboteur MUST be a JSON boolean: true or false.",
                "clues on a player MUST be a JSON array of strings.",
                "Every global clue owner_player_id MUST reference an existing player_id.",
                "Every event player_ids value MUST contain existing player_ids.",
                "All player-facing text must be in Dutch.",
                "Role names must exactly match the available role pool.",
                "Generate phases, delayed events, voting moments, clue dependencies and a truth model.",
            ],
        }

        body = {
            "model": settings.ai_model,
            "temperature": 0.2,
            "include_reasoning": False,
            "reasoning_effort": "low",
            "max_completion_tokens": 65536,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional tabletop game designer. "
                        "Return ONLY the requested JSON game object. "
                        "The generated game MUST contain game_id, game_name, "
                        "title, story, objective, rules, difficulty, "
                        "solution, players, duration, saboteur_count, "
                        "team_win_condition, individual_win_condition, "
                        "saboteur_win_condition, truth_model, phases, "
                        "events, voting_moments and clues. "
                        "game_id is an immutable canonical identifier and "
                        "MUST exactly match the provided game_id. "
                        "Never translate, capitalize, rename, or modify it. "
                        "game_name MUST exactly match the provided game_name. "
                        "difficulty must be exactly easy, medium, or hard. "
                        "duration MUST exactly match the requested duration. "
                        "solution and truth_model are secret canonical "
                        "information and must never be shown to normal players. "
                        "personal_objectives MUST be a JSON array of objective "
                        "objects matching the requested structure. "
                        "relationships MUST be a JSON array of strings, "
                        "never an object or dictionary. "
                        "is_saboteur MUST be a JSON boolean."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": prompt,
                            "output_requirements": {
                                "required_fields": [
                                    "game_id",
                                    "game_name",
                                    "title",
                                    "story",
                                    "objective",
                                    "rules",
                                    "players",
                                    "solution",
                                    "difficulty",
                                    "duration",
                                    "saboteur_count",
                                    "team_win_condition",
                                    "individual_win_condition",
                                    "saboteur_win_condition",
                                    "truth_model",
                                    "phases",
                                    "events",
                                    "voting_moments",
                                    "clues",
                                ],
                                "player_required_fields": [
                                    "player_id",
                                    "name",
                                    "role",
                                    "role_description",
                                    "objective",
                                    "personal_objectives",
                                    "secret_information",
                                    "clues",
                                    "relationships",
                                    "instructions",
                                    "is_saboteur",
                                ],
                                "personal_objective_required_fields": [
                                    "id",
                                    "text",
                                    "owner_player_id",
                                    "measurable",
                                    "metric",
                                    "target_player_id",
                                    "target_value",
                                    "activate_phase",
                                ],
                                "difficulty": [
                                    "easy",
                                    "medium",
                                    "hard",
                                ],
                                "duration": [
                                    "avond",
                                    "1_week",
                                    "2_weken",
                                    "3_weken",
                                    "1_maand",
                                ],
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "response_format": {
                "type": "json_object",
            },
        }

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(timeout=45) as client:
                    response = await client.post(
                        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                        json=body,
                        headers=headers,
                    )

                    response.raise_for_status()

                    response_data = response.json()

                    content = response_data["choices"][0]["message"]["content"]

                    if not isinstance(content, str):
                        raise ValueError(
                            "AI returned non-string message content"
                        )

                    raw = json.loads(content)

                    if hasattr(GeneratedGame, "model_validate"):
                        generated = GeneratedGame.model_validate(raw)
                    else:
                        generated = GeneratedGame.parse_obj(raw)

                    _validate_generation(
                        generated,
                        game,
                        names,
                        clue_count,
                        difficulty,
                        duration,
                    )

                    return generated

            except ValidationError as exc:
                logger.error(
                    "AI generation validation failed on attempt %s: %s",
                    attempt,
                    exc.errors(),
                )
                last_error = exc

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code

                logger.error(
                    "Groq API error %s: %s",
                    status,
                    exc.response.text[:4000],
                )

                last_error = exc

                if status not in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }:
                    break

            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.exception(
                    "AI game generation request failed on attempt %s",
                    attempt,
                )
                last_error = exc

            if attempt < 3:
                await asyncio.sleep(0.5 * attempt)

        raise RuntimeError(
            f"AI_GAME_GENERATION_FAILED: {last_error}"
        ) from last_error


def _validate_generation(
    generated: GeneratedGame,
    game: dict[str, Any],
    names: list[str],
    clue_count: int,
    requested_difficulty: str,
    requested_duration: str,
) -> None:
    # Canonical game information
    if generated.game_id != game["id"]:
        raise ValueError(
            "canonical game_id must match selected game"
        )

    if generated.game_name != game["name"]:
        raise ValueError(
            "canonical game_name must match selected game"
        )

    if generated.difficulty != requested_difficulty:
        raise ValueError(
            f"expected difficulty {requested_difficulty}, "
            f"received {generated.difficulty}"
        )

    if generated.duration != requested_duration:
        raise ValueError(
            f"expected duration {requested_duration}, "
            f"received {generated.duration}"
        )

    if not generated.solution.strip():
        raise ValueError("solution cannot be empty")

    if not generated.truth_model.strip():
        raise ValueError("truth_model cannot be empty")

    # Players
    if len(generated.players) != len(names):
        raise ValueError(
            f"expected {len(names)} players, "
            f"received {len(generated.players)}"
        )

    expected_player_ids = {
        str(index + 1)
        for index in range(len(names))
    }

    actual_player_ids = {
        player.player_id
        for player in generated.players
    }

    if actual_player_ids != expected_player_ids:
        raise ValueError(
            "player_id values must be unique and sequential"
        )

    role_names = {
        role["name"]
        for role in game["roles"]
    }

    for index, player in enumerate(generated.players):
        expected_id = str(index + 1)
        expected_name = names[index]

        if player.player_id != expected_id:
            raise ValueError(
                f"player {index + 1} has invalid player_id"
            )

        if player.name != expected_name:
            raise ValueError(
                f"player {index + 1} has invalid name"
            )

        if player.role not in role_names:
            raise ValueError(
                f"player {index + 1} has invalid role: {player.role}"
            )

        if len(player.clues) < max(1, clue_count):
            raise ValueError(
                f"player {index + 1} has insufficient clues"
            )

        if not player.personal_objectives:
            raise ValueError(
                f"player {index + 1} has no personal objectives"
            )

        for objective in player.personal_objectives:
            if objective.owner_player_id != player.player_id:
                raise ValueError(
                    f"objective {objective.id} belongs to "
                    f"{objective.owner_player_id}, but is assigned to "
                    f"{player.player_id}"
                )

    # Saboteur count
    actual_saboteurs = sum(
        1
        for player in generated.players
        if player.is_saboteur
    )

    if generated.saboteur_count != actual_saboteurs:
        raise ValueError(
            "saboteur_count does not match player assignments"
        )

    if generated.saboteur_count < 1:
        raise ValueError(
            "at least one saboteur is required"
        )

    # Duration requirements
    minimum_phases = (
        5
        if requested_duration == "1_maand"
        else 3
        if requested_duration in {"2_weken", "3_weken"}
        else 1
    )

    minimum_votes = (
        3
        if requested_duration == "1_maand"
        else 2
        if requested_duration in {"2_weken", "3_weken"}
        else 1
    )

    if len(generated.phases) < minimum_phases:
        raise ValueError(
            f"duration requires at least {minimum_phases} phases"
        )

    if len(generated.voting_moments) < minimum_votes:
        raise ValueError(
            f"duration requires at least {minimum_votes} voting moments"
        )

    # Phase IDs
    phase_numbers = {
        phase.number
        for phase in generated.phases
    }

    if len(phase_numbers) != len(generated.phases):
        raise ValueError(
            "phase numbers must be unique"
        )

    # Voting moments
    voting_ids = [
        voting.id
        for voting in generated.voting_moments
    ]

    if len(voting_ids) != len(set(voting_ids)):
        raise ValueError(
            "voting moment IDs must be unique"
        )

    for voting in generated.voting_moments:
        if voting.phase not in phase_numbers:
            raise ValueError(
                f"voting moment {voting.id} references "
                f"unknown phase {voting.phase}"
            )

    # Events
    event_ids = [
        event.id
        for event in generated.events
    ]

    if len(event_ids) != len(set(event_ids)):
        raise ValueError(
            "event IDs must be unique"
        )

    for event in generated.events:
        if event.phase not in phase_numbers:
            raise ValueError(
                f"event {event.id} references "
                f"unknown phase {event.phase}"
            )

        for player_id in event.player_ids:
            if player_id not in actual_player_ids:
                raise ValueError(
                    f"event {event.id} references unknown player "
                    f"{player_id}"
                )

    # Global clues
    clue_ids = [
        clue.id
        for clue in generated.clues
    ]

    if len(clue_ids) != len(set(clue_ids)):
        raise ValueError(
            "clue IDs must be unique"
        )

    minimum_global_clues = (
        len(names) * max(1, clue_count)
    )

    if len(generated.clues) < minimum_global_clues:
        raise ValueError(
            f"expected at least {minimum_global_clues} global clues, "
            f"received {len(generated.clues)}"
        )

    for clue in generated.clues:
        if clue.owner_player_id not in actual_player_ids:
            raise ValueError(
                f"clue {clue.id} references unknown owner "
                f"{clue.owner_player_id}"
            )

        if clue.release_phase not in phase_numbers:
            raise ValueError(
                f"clue {clue.id} references unknown phase "
                f"{clue.release_phase}"
            )

        for dependency in clue.dependencies:
            if dependency not in clue_ids:
                raise ValueError(
                    f"clue {clue.id} references unknown "
                    f"dependency {dependency}"
                )

    # Player clue count
    for index, player in enumerate(generated.players):
        if len(player.clues) < max(1, clue_count):
            raise ValueError(
                f"player {index + 1} has insufficient player clues"
            )


ai_service = AIService()