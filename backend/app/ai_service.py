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
            "language": "Nederlands",
            "requirements": [
                "Return ONLY valid JSON.",
                "Do not return markdown.",
                "Generate exactly one player per requested name.",
                "Use exactly the requested player IDs.",
                "Use exactly one role from available_roles per player.",
                "personal_objectives must be arrays.",
                "relationships must be arrays of strings.",
                "is_saboteur must be boolean.",
                "phases must use numbered phases.",
                "events must reference numbered phases.",
                "voting moments must reference numbered phases.",
                "clues must reference numbered phases.",
                "All player-facing text must be Dutch.",
            ],
        }

        system_prompt = (
            "You are a professional tabletop game designer. "
            "Return ONLY one valid JSON game object. "
            "Do not use markdown or code fences. "
            "Follow output_requirements exactly. "
            "All phase references use integer phase numbers, never phase names. "
            "Use id for IDs, never phase_id, event_id, voting_id or clue_id. "
            "Use title for event titles. "
            "Use question for voting questions. "
            "Use text for clue text. "
            "relationships must always be an array of strings. "
            "personal_objectives must always be an array of objects. "
            "metric must be one of the allowed metric values. "
            "activate_phase must always be an integer."
        )

        body = {
            "model": settings.ai_model,
            "temperature": 0.2,
            "include_reasoning": False,
            "reasoning_effort": "low",
            "max_completion_tokens": 65536,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
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
                                "phase_required_fields": [
                                    "number",
                                    "name",
                                    "purpose",
                                    "open_question",
                                    "release_after_days",
                                    "objectives",
                                ],
                                "event_required_fields": [
                                    "id",
                                    "phase",
                                    "title",
                                    "description",
                                    "delivery",
                                    "release_after_days",
                                    "player_ids",
                                ],
                                "voting_required_fields": [
                                    "id",
                                    "phase",
                                    "question",
                                    "release_after_days",
                                    "duration_hours",
                                ],
                                "clue_required_fields": [
                                    "id",
                                    "text",
                                    "clue_type",
                                    "owner_player_id",
                                    "release_phase",
                                    "visibility",
                                    "supports",
                                    "dependencies",
                                    "red_herring",
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

                    # BELANGRIJK:
                    # Normaliseer de structuur van het model voordat
                    # Pydantic hem valideert.
                    raw = _normalize_generation(
                        raw,
                        names=names,
                    )

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


def _phase_number(value: Any, phases: list[dict[str, Any]]) -> int:
    """Convert phase names/IDs/numbers into our internal integer phase."""

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        value_lower = value.lower().strip()

        if value_lower.isdigit():
            return int(value_lower)

        for index, phase in enumerate(phases, start=1):
            phase_id = str(
                phase.get("phase_id", phase.get("id", ""))
            ).lower()

            phase_name = str(
                phase.get("name", "")
            ).lower()

            if value_lower in {
                phase_id,
                phase_name,
            }:
                return index

    return 1


def _normalize_generation(
    raw: dict[str, Any],
    *,
    names: list[str],
) -> dict[str, Any]:
    """
    Normalize common GPT output variations into the exact internal schema.

    The model sometimes naturally generates:
      phase_id -> number
      event_id -> id
      voting_id -> id
      clue_id -> id
      event.name -> title
      phase names instead of phase numbers

    This converts those forms before Pydantic validation.
    """

    if not isinstance(raw, dict):
        raise ValueError("AI output must be a JSON object")

    # ---------------------------------------------------------
    # PHASES
    # ---------------------------------------------------------

    phases = raw.get("phases", [])

    if not isinstance(phases, list):
        phases = []

    normalized_phases = []

    for index, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict):
            continue

        phase_name = str(
            phase.get(
                "name",
                phase.get(
                    "phase_name",
                    phase.get(
                        "phase_id",
                        f"Fase {index}",
                    ),
                ),
            )
        )

        normalized_phases.append(
            {
                "number": index,
                "name": phase_name,
                "purpose": str(
                    phase.get(
                        "purpose",
                        phase.get(
                            "description",
                            phase.get(
                                "goal",
                                phase_name,
                            ),
                        ),
                    )
                ),
                "open_question": str(
                    phase.get(
                        "open_question",
                        phase.get(
                            "question",
                            "Wat gebeurt er in deze fase?",
                        ),
                    )
                ),
                "release_after_days": _safe_int(
                    phase.get(
                        "release_after_days",
                        0,
                    ),
                    0,
                ),
                "objectives": _string_list(
                    phase.get(
                        "objectives",
                        phase.get(
                            "goals",
                            ["Onderzoek de situatie."],
                        ),
                    )
                ),
            }
        )

    raw["phases"] = normalized_phases

    # ---------------------------------------------------------
    # PLAYER DATA
    # ---------------------------------------------------------

    players = raw.get("players", [])

    if not isinstance(players, list):
        players = []

    # First collect global clues. Player clues can be populated
    # from these if the model leaves them empty.
    global_clues = raw.get("clues", [])

    if not isinstance(global_clues, list):
        global_clues = []

    global_clue_texts = []

    for clue in global_clues:
        if isinstance(clue, dict):
            text = clue.get("text", clue.get("description", ""))
            if text:
                global_clue_texts.append(str(text))
        elif isinstance(clue, str):
            global_clue_texts.append(clue)

    normalized_players = []

    for index, player in enumerate(players):
        if not isinstance(player, dict):
            continue

        player_id = str(
            player.get(
                "player_id",
                index + 1,
            )
        )

        player_name = str(
            player.get(
                "name",
                names[index] if index < len(names) else f"Speler {index + 1}",
            )
        )

        # -------------------------
        # Relationships
        # -------------------------

        relationships = player.get(
            "relationships",
            [],
        )

        if isinstance(relationships, dict):
            relationships = [
                f"{key}: {value}"
                for key, value in relationships.items()
            ]
        elif isinstance(relationships, str):
            relationships = [relationships]
        elif not isinstance(relationships, list):
            relationships = []

        relationships = [
            str(item)
            for item in relationships
        ]

        # -------------------------
        # Clues
        # -------------------------

        player_clues = player.get(
            "clues",
            [],
        )

        if isinstance(player_clues, str):
            player_clues = [player_clues]

        if not isinstance(player_clues, list):
            player_clues = []

        player_clues = [
            str(item)
            for item in player_clues
            if str(item).strip()
        ]

        # If AI didn't put clues on players,
        # use global clue texts so validation doesn't fail.
        if len(player_clues) < 2:
            for clue_text in global_clue_texts:
                if clue_text not in player_clues:
                    player_clues.append(clue_text)

                if len(player_clues) >= 2:
                    break

        # -------------------------
        # Personal objectives
        # -------------------------

        objectives = player.get(
            "personal_objectives",
            [],
        )

        if isinstance(objectives, dict):
            objectives = [objectives]

        if not isinstance(objectives, list):
            objectives = []

        normalized_objectives = []

        for objective_index, objective in enumerate(objectives):
            if not isinstance(objective, dict):
                continue

            metric = objective.get(
                "metric",
                "manual_review",
            )

            metric_map = {
                "clues": "clue_found",
                "clue": "clue_found",
                "find_clue": "clue_found",
                "votes": "vote_received",
                "vote": "vote_received",
                "suspected": "top_suspect",
                "avoid_suspicion": "not_top_suspect",
                "theory": "theory_adopted",
                "change_vote": "vote_change",
                "manual": "manual_review",
            }

            metric = metric_map.get(
                str(metric).lower(),
                metric,
            )

            allowed_metrics = {
                "vote_received",
                "top_suspect",
                "not_top_suspect",
                "mutual_suspicion",
                "theory_adopted",
                "vote_change",
                "clue_found",
                "manual_review",
            }

            if metric not in allowed_metrics:
                metric = "manual_review"

            activate_phase = objective.get(
                "activate_phase",
                1,
            )

            # "planning", "execution", "escape", etc.
            # moeten integers worden.
            activate_phase = _phase_number(
                activate_phase,
                phases,
            )

            normalized_objectives.append(
                {
                    "id": str(
                        objective.get(
                            "id",
                            f"{player_id}-objective-{objective_index + 1}",
                        )
                    ),
                    "text": str(
                        objective.get(
                            "text",
                            objective.get(
                                "description",
                                objective.get(
                                    "objective",
                                    "Bereik je persoonlijke doel.",
                                ),
                            ),
                        )
                    ),
                    "owner_player_id": player_id,
                    "measurable": bool(
                        objective.get(
                            "measurable",
                            False,
                        )
                    ),
                    "metric": metric,
                    "target_player_id": (
                        str(objective["target_player_id"])
                        if objective.get("target_player_id") is not None
                        else None
                    ),
                    "target_value": (
                        _safe_int(objective["target_value"], None)
                        if objective.get("target_value") is not None
                        else None
                    ),
                    "activate_phase": activate_phase,
                }
            )

        if not normalized_objectives:
            normalized_objectives.append(
                {
                    "id": f"{player_id}-objective-1",
                    "text": str(
                        player.get(
                            "objective",
                            "Bereik je persoonlijke doel.",
                        )
                    ),
                    "owner_player_id": player_id,
                    "measurable": False,
                    "metric": "manual_review",
                    "target_player_id": None,
                    "target_value": None,
                    "activate_phase": 1,
                }
            )

        normalized_players.append(
            {
                "player_id": player_id,
                "name": player_name,
                "role": str(
                    player.get(
                        "role",
                        "Player",
                    )
                ),
                "role_description": str(
                    player.get(
                        "role_description",
                        player.get(
                            "description",
                            "",
                        ),
                    )
                ),
                "objective": str(
                    player.get(
                        "objective",
                        "Bereik je persoonlijke doel.",
                    )
                ),
                "personal_objectives": normalized_objectives,
                "secret_information": str(
                    player.get(
                        "secret_information",
                        player.get(
                            "secret",
                            "",
                        ),
                    )
                ),
                "clues": player_clues,
                "relationships": relationships,
                "instructions": str(
                    player.get(
                        "instructions",
                        "",
                    )
                ),
                "is_saboteur": bool(
                    player.get(
                        "is_saboteur",
                        False,
                    )
                ),
            }
        )

    raw["players"] = normalized_players

    # ---------------------------------------------------------
    # EVENTS
    # ---------------------------------------------------------

    events = raw.get("events", [])

    if not isinstance(events, list):
        events = []

    normalized_events = []

    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue

        player_ids = event.get(
            "player_ids",
            [],
        )

        if isinstance(player_ids, str):
            player_ids = [player_ids]

        if not isinstance(player_ids, list):
            player_ids = []

        # Events cannot have an empty player_ids list.
        if not player_ids:
            player_ids = [
                str(index)
                if index <= len(names)
                else "1"
            ]

        normalized_events.append(
            {
                "id": str(
                    event.get(
                        "id",
                        event.get(
                            "event_id",
                            f"event-{index}",
                        ),
                    )
                ),
                "phase": _phase_number(
                    event.get(
                        "phase",
                        event.get(
                            "phase_id",
                            1,
                        ),
                    ),
                    phases,
                ),
                "title": str(
                    event.get(
                        "title",
                        event.get(
                            "name",
                            f"Event {index}",
                        ),
                    )
                ),
                "description": str(
                    event.get(
                        "description",
                        event.get(
                            "details",
                            "",
                        ),
                    )
                ),
                "delivery": _normalize_delivery(
                    event.get(
                        "delivery",
                        "website",
                    )
                ),
                "release_after_days": _safe_int(
                    event.get(
                        "release_after_days",
                        0,
                    ),
                    0,
                ),
                "player_ids": [
                    str(player_id)
                    for player_id in player_ids
                ],
            }
        )

    raw["events"] = normalized_events

    # ---------------------------------------------------------
    # VOTING MOMENTS
    # ---------------------------------------------------------

    voting_moments = raw.get(
        "voting_moments",
        [],
    )

    if not isinstance(voting_moments, list):
        voting_moments = []

    normalized_votes = []

    for index, voting in enumerate(
        voting_moments,
        start=1,
    ):
        if not isinstance(voting, dict):
            continue

        normalized_votes.append(
            {
                "id": str(
                    voting.get(
                        "id",
                        voting.get(
                            "voting_id",
                            f"vote-{index}",
                        ),
                    )
                ),
                "phase": _phase_number(
                    voting.get(
                        "phase",
                        voting.get(
                            "phase_id",
                            1,
                        ),
                    ),
                    phases,
                ),
                "question": str(
                    voting.get(
                        "question",
                        voting.get(
                            "name",
                            "Wie verdenken jullie?",
                        ),
                    )
                ),
                "release_after_days": _safe_int(
                    voting.get(
                        "release_after_days",
                        0,
                    ),
                    0,
                ),
                "duration_hours": max(
                    1,
                    min(
                        168,
                        _safe_int(
                            voting.get(
                                "duration_hours",
                                24,
                            ),
                            24,
                        ),
                    ),
                ),
            }
        )

    raw["voting_moments"] = normalized_votes

    # ---------------------------------------------------------
    # CLUES
    # ---------------------------------------------------------

    normalized_clues = []

    for index, clue in enumerate(
        global_clues,
        start=1,
    ):
        if not isinstance(clue, dict):
            continue

        clue_phase = clue.get(
            "release_phase",
            clue.get(
                "phase",
                clue.get(
                    "phase_id",
                    1,
                ),
            ),
        )

        clue_type = clue.get(
            "clue_type",
            "direct",
        )

        allowed_clue_types = {
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
        }

        if clue_type not in allowed_clue_types:
            clue_type = "direct"

        supports = clue.get(
            "supports",
            [],
        )

        if isinstance(supports, str):
            supports = [supports]

        if not isinstance(supports, list):
            supports = []

        if not supports:
            supports = ["solution"]

        dependencies = clue.get(
            "dependencies",
            [],
        )

        if isinstance(dependencies, str):
            dependencies = [dependencies]

        if not isinstance(dependencies, list):
            dependencies = []

        normalized_clues.append(
            {
                "id": str(
                    clue.get(
                        "id",
                        clue.get(
                            "clue_id",
                            f"clue-{index}",
                        ),
                    )
                ),
                "text": str(
                    clue.get(
                        "text",
                        clue.get(
                            "description",
                            "",
                        ),
                    )
                ),
                "clue_type": clue_type,
                "owner_player_id": str(
                    clue.get(
                        "owner_player_id",
                        "1",
                    )
                ),
                "release_phase": _phase_number(
                    clue_phase,
                    phases,
                ),
                "visibility": _normalize_visibility(
                    clue.get(
                        "visibility",
                        "public",
                    )
                ),
                "supports": [
                    str(item)
                    for item in supports
                ],
                "dependencies": [
                    str(item)
                    for item in dependencies
                ],
                "red_herring": bool(
                    clue.get(
                        "red_herring",
                        False,
                    )
                ),
            }
        )

    raw["clues"] = normalized_clues

    return raw


def _safe_int(
    value: Any,
    default: int | None,
) -> int | None:
    try:
        if value is None:
            return default

        return int(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]

    if not isinstance(value, list):
        return []

    result = [
        str(item)
        for item in value
        if str(item).strip()
    ]

    return result or ["Onderzoek de situatie."]


def _normalize_delivery(value: Any) -> str:
    allowed = {
        "website",
        "email",
        "physical_clue",
        "qr_code",
        "whatsapp",
        "printed_document",
    }

    value = str(value).lower().strip()

    mapping = {
        "web": "website",
        "site": "website",
        "mail": "email",
        "physical": "physical_clue",
        "physical clue": "physical_clue",
        "qr": "qr_code",
        "document": "printed_document",
        "print": "printed_document",
    }

    value = mapping.get(value, value)

    return value if value in allowed else "website"


def _normalize_visibility(value: Any) -> str:
    allowed = {
        "public",
        "private",
        "shareable",
    }

    value = str(value).lower().strip()

    mapping = {
        "shared": "shareable",
        "everyone": "public",
        "all": "public",
        "secret": "private",
    }

    value = mapping.get(value, value)

    return value if value in allowed else "public"


def _validate_generation(
    generated: GeneratedGame,
    game: dict[str, Any],
    names: list[str],
    clue_count: int,
    requested_difficulty: str,
    requested_duration: str,
) -> None:
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

    for index, player in enumerate(
        generated.players
    ):
        if player.player_id != str(index + 1):
            raise ValueError(
                f"player {index + 1} has invalid player_id"
            )

        if player.name != names[index]:
            raise ValueError(
                f"player {index + 1} has invalid name"
            )

        if player.role not in role_names:
            raise ValueError(
                f"player {index + 1} has invalid role: "
                f"{player.role}"
            )

        if len(player.clues) < max(1, clue_count):
            raise ValueError(
                f"player {index + 1} has insufficient clues"
            )

        if not player.personal_objectives:
            raise ValueError(
                f"player {index + 1} has no personal objective"
            )

        for objective in player.personal_objectives:
            if objective.owner_player_id != player.player_id:
                raise ValueError(
                    f"objective {objective.id} belongs to "
                    f"{objective.owner_player_id}, but is assigned "
                    f"to {player.player_id}"
                )

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

    phase_numbers = {
        phase.number
        for phase in generated.phases
    }

    if len(phase_numbers) != len(generated.phases):
        raise ValueError(
            "phase numbers must be unique"
        )

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
                    f"event {event.id} references "
                    f"unknown player {player_id}"
                )

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


ai_service = AIService()