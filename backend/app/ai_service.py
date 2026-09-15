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


Duration = Literal[
    "avond",
    "1_week",
    "2_weken",
    "3_weken",
    "1_maand",
]


Metric = Literal[
    "vote_received",
    "top_suspect",
    "not_top_suspect",
    "mutual_suspicion",
    "theory_adopted",
    "vote_change",
    "clue_found",
    "manual_review",
]


ClueType = Literal[
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


Delivery = Literal[
    "website",
    "email",
    "physical_clue",
    "qr_code",
    "whatsapp",
    "printed_document",
]


Visibility = Literal[
    "public",
    "private",
    "shareable",
]


class GeneratedClue(BaseModel):
    id: str
    text: str
    clue_type: ClueType
    owner_player_id: str
    release_phase: int = Field(ge=1)
    visibility: Visibility
    supports: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    red_herring: bool = False


class GeneratedObjective(BaseModel):
    id: str
    text: str
    owner_player_id: str
    measurable: bool
    metric: Metric
    target_player_id: str | None = None
    target_value: int | None = None
    activate_phase: int = Field(ge=1)


class GeneratedPlayer(BaseModel):
    model_config = {
        "extra": "forbid",
    }

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
    delivery: Delivery
    release_after_days: int = Field(ge=0)
    player_ids: list[str] = Field(min_length=1)


class GeneratedVotingMoment(BaseModel):
    id: str
    phase: int = Field(ge=1)
    question: str
    release_after_days: int = Field(ge=0)
    duration_hours: int = Field(ge=1, le=168)


class GeneratedGame(BaseModel):
    model_config = {
        "extra": "forbid",
    }

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


# ============================================================
# AI SERVICE
# ============================================================


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

        if not names:
            raise ValueError("At least one player is required.")

        clue_count = max(2, int(clue_count))

        prompt = {
            "game_id": game["id"],
            "game_name": game["name"],
            "game_rules": game["rules"],
            "available_roles": [
                role["name"]
                for role in game["roles"]
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
            "clue_count_per_player": clue_count,
            "minimum_total_clues": len(names) * clue_count,
            "language": "Nederlands",
            "requirements": [
                "Return ONLY valid JSON.",
                "Do not return markdown.",
                "Generate exactly one player per requested name.",
                "Use exactly the requested player IDs.",
                "Use exactly one role from available_roles per player.",
                "personal_objectives must be arrays of objects.",
                "relationships must be arrays of strings.",
                "is_saboteur must be boolean.",
                "phases must use integer number fields starting at 1.",
                "events must reference integer phase numbers.",
                "voting moments must reference integer phase numbers.",
                "clues must reference integer release_phase numbers.",
                f"Every player MUST have at least {clue_count} clue texts.",
                f"Generate at least {len(names) * clue_count} global clues.",
                "Every global clue must have an owner_player_id.",
                "All player-facing text must be Dutch.",
            ],
        }

        system_prompt = (
            "You are a professional tabletop game designer. "
            "Return ONLY one valid JSON game object. "
            "Do not use markdown or code fences. "
            "Follow output_requirements exactly. "
            "All phase references must be integers, never phase names. "
            "Use id for IDs, never phase_id, event_id, voting_id or clue_id. "
            "Use number for phase numbers. "
            "Use title for event titles. "
            "Use question for voting questions. "
            "Use text for clue text. "
            "relationships must always be an array of strings. "
            "personal_objectives must always be an array of objects. "
            "metric must be one of the allowed metric values. "
            "activate_phase must always be an integer. "
            "Every player must receive the requested number of clues. "
            "The global clues array must contain enough clues for every player."
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
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                        json=body,
                        headers=headers,
                    )

                    response.raise_for_status()

                    response_data = response.json()

                    content = (
                        response_data["choices"][0]["message"]["content"]
                    )

                    if not isinstance(content, str):
                        raise ValueError(
                            "AI returned non-string message content"
                        )

                    raw = json.loads(content)

                    raw = _normalize_generation(
                        raw,
                        names=names,
                        clue_count=clue_count,
                        requested_duration=duration,
                    )

                    generated = GeneratedGame.model_validate(raw)

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
                    "AI API error %s: %s",
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

            except (
                httpx.HTTPError,
                KeyError,
                ValueError,
                TypeError,
            ) as exc:
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


# ============================================================
# NORMALIZATION
# ============================================================


def _phase_number(
    value: Any,
    phases: list[dict[str, Any]],
) -> int:
    """
    Convert phase names, IDs or numeric strings to integer phase numbers.
    """

    if isinstance(value, bool):
        return 1

    if isinstance(value, int):
        return max(1, value)

    if isinstance(value, float):
        return max(1, int(value))

    if isinstance(value, str):
        value_lower = value.lower().strip()

        if value_lower.isdigit():
            return max(1, int(value_lower))

        for index, phase in enumerate(
            phases,
            start=1,
        ):
            if not isinstance(phase, dict):
                continue

            phase_id = str(
                phase.get(
                    "phase_id",
                    phase.get("id", ""),
                )
            ).lower().strip()

            phase_name = str(
                phase.get(
                    "name",
                    phase.get("phase_name", ""),
                )
            ).lower().strip()

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
    clue_count: int,
    requested_duration: str,
) -> dict[str, Any]:

    if not isinstance(raw, dict):
        raise ValueError(
            "AI output must be a JSON object"
        )

    clue_count = max(
        2,
        int(clue_count),
    )

    # ========================================================
    # PHASES
    # ========================================================

    original_phases = raw.get(
        "phases",
        [],
    )

    if not isinstance(original_phases, list):
        original_phases = []

    minimum_phases = _minimum_phases(
        requested_duration
    )

    normalized_phases: list[dict[str, Any]] = []

    for index, phase in enumerate(
        original_phases,
        start=1,
    ):
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
        ).strip()

        if not phase_name:
            phase_name = f"Fase {index}"

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
                                "Onderzoek de situatie.",
                            ),
                        ),
                    )
                ),
                "open_question": str(
                    phase.get(
                        "open_question",
                        phase.get(
                            "question",
                            "Wat is er werkelijk gebeurd?",
                        ),
                    )
                ),
                "release_after_days": max(
                    0,
                    _safe_int(
                        phase.get(
                            "release_after_days",
                            0,
                        ),
                        0,
                    ),
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

    # Als AI geen fases geeft, maken we ze zelf.
    if not normalized_phases:
        normalized_phases = [
            {
                "number": 1,
                "name": "Start",
                "purpose": "Verzamel informatie en onderzoek de situatie.",
                "open_question": "Wat is er werkelijk gebeurd?",
                "release_after_days": 0,
                "objectives": [
                    "Verzamel aanwijzingen.",
                    "Bespreek je theorieën.",
                ],
            }
        ]

    # Voeg ontbrekende fases toe.
    while len(normalized_phases) < minimum_phases:
        number = len(normalized_phases) + 1

        normalized_phases.append(
            {
                "number": number,
                "name": _default_phase_name(number),
                "purpose": _default_phase_purpose(number),
                "open_question": _default_phase_question(number),
                "release_after_days": _default_release_day(
                    number,
                    requested_duration,
                ),
                "objectives": [
                    "Onderzoek de nieuwe informatie.",
                    "Vergelijk je theorie met die van andere spelers.",
                ],
            }
        )

    # Forceer correcte opeenvolgende nummers.
    for index, phase in enumerate(
        normalized_phases,
        start=1,
    ):
        phase["number"] = index

    raw["phases"] = normalized_phases

    # ========================================================
    # PLAYERS
    # ========================================================

    original_players = raw.get(
        "players",
        [],
    )

    if not isinstance(original_players, list):
        original_players = []

    global_clues_raw = raw.get(
        "clues",
        [],
    )

    if not isinstance(global_clues_raw, list):
        global_clues_raw = []

    normalized_players: list[dict[str, Any]] = []

    for index, name in enumerate(names):
        source = (
            original_players[index]
            if index < len(original_players)
            and isinstance(original_players[index], dict)
            else {}
        )

        player_id = str(index + 1)

        player_name = name

        # ====================================================
        # RELATIONSHIPS
        # ====================================================

        relationships = source.get(
            "relationships",
            [],
        )

        if isinstance(relationships, dict):
            relationships = [
                f"{key}: {value}"
                for key, value in relationships.items()
            ]

        elif isinstance(relationships, str):
            relationships = [
                relationships
            ]

        elif not isinstance(relationships, list):
            relationships = []

        relationships = [
            str(item).strip()
            for item in relationships
            if str(item).strip()
        ]

        # ====================================================
        # PLAYER CLUES
        # ====================================================

        player_clues = source.get(
            "clues",
            [],
        )

        if isinstance(player_clues, str):
            player_clues = [
                player_clues
            ]

        if not isinstance(player_clues, list):
            player_clues = []

        player_clues = [
            str(item).strip()
            for item in player_clues
            if str(item).strip()
        ]

        # Ook oude AI-output kan clues als objecten bevatten.
        cleaned_player_clues: list[str] = []

        for clue in player_clues:
            if isinstance(clue, dict):
                text = clue.get(
                    "text",
                    clue.get(
                        "description",
                        "",
                    ),
                )

                if text:
                    cleaned_player_clues.append(
                        str(text).strip()
                    )
            else:
                cleaned_player_clues.append(
                    str(clue).strip()
                )

        player_clues = cleaned_player_clues

        # Eerst proberen we clues uit de globale lijst.
        for clue in global_clues_raw:
            if len(player_clues) >= clue_count:
                break

            if isinstance(clue, dict):
                owner = str(
                    clue.get(
                        "owner_player_id",
                        "",
                    )
                )

                text = clue.get(
                    "text",
                    clue.get(
                        "description",
                        "",
                    ),
                )

                if (
                    text
                    and (
                        not owner
                        or owner == player_id
                    )
                ):
                    text = str(text).strip()

                    if text not in player_clues:
                        player_clues.append(text)

        # Als AI nog steeds te weinig clues heeft:
        # maak geldige fallback clues.
        fallback_index = 1

        while len(player_clues) < clue_count:
            fallback = (
                f"Aanwijzing voor {player_name}: "
                f"zoek naar inconsistenties in de verklaringen "
                f"van de andere spelers "
                f"(aanwijzing {fallback_index})."
            )

            if fallback not in player_clues:
                player_clues.append(fallback)

            fallback_index += 1

        # ====================================================
        # PERSONAL OBJECTIVES
        # ====================================================

        objectives = source.get(
            "personal_objectives",
            [],
        )

        if isinstance(objectives, dict):
            objectives = [
                objectives
            ]

        if not isinstance(objectives, list):
            objectives = []

        normalized_objectives: list[dict[str, Any]] = []

        for objective_index, objective in enumerate(
            objectives,
            start=1,
        ):
            if not isinstance(objective, dict):
                continue

            metric = _normalize_metric(
                objective.get(
                    "metric",
                    "manual_review",
                )
            )

            activate_phase = _phase_number(
                objective.get(
                    "activate_phase",
                    objective.get(
                        "phase",
                        1,
                    ),
                ),
                original_phases,
            )

            activate_phase = max(
                1,
                min(
                    len(normalized_phases),
                    activate_phase,
                ),
            )

            normalized_objectives.append(
                {
                    "id": str(
                        objective.get(
                            "id",
                            f"{player_id}-objective-{objective_index}",
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
                        str(
                            objective["target_player_id"]
                        )
                        if objective.get(
                            "target_player_id"
                        ) is not None
                        else None
                    ),
                    "target_value": (
                        _safe_int(
                            objective.get(
                                "target_value"
                            ),
                            None,
                        )
                        if objective.get(
                            "target_value"
                        ) is not None
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
                        source.get(
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

        # ====================================================
        # PLAYER
        # ====================================================

        normalized_players.append(
            {
                "player_id": player_id,
                "name": player_name,
                "role": str(
                    source.get(
                        "role",
                        "Player",
                    )
                ),
                "role_description": str(
                    source.get(
                        "role_description",
                        source.get(
                            "description",
                            "Een deelnemer aan het spel.",
                        ),
                    )
                ),
                "objective": str(
                    source.get(
                        "objective",
                        "Help je team en bereik je persoonlijke doel.",
                    )
                ),
                "personal_objectives": normalized_objectives,
                "secret_information": str(
                    source.get(
                        "secret_information",
                        source.get(
                            "secret",
                            "",
                        ),
                    )
                ),
                "clues": player_clues,
                "relationships": relationships,
                "instructions": str(
                    source.get(
                        "instructions",
                        "Speel je rol en deel informatie wanneer dat strategisch verstandig is.",
                    )
                ),
                "is_saboteur": bool(
                    source.get(
                        "is_saboteur",
                        False,
                    )
                ),
            }
        )

    raw["players"] = normalized_players

    # ========================================================
    # EVENTS
    # ========================================================

    original_events = raw.get(
        "events",
        [],
    )

    if not isinstance(original_events, list):
        original_events = []

    normalized_events: list[dict[str, Any]] = []

    player_ids = [
        str(index + 1)
        for index in range(len(names))
    ]

    for index, event in enumerate(
        original_events,
        start=1,
    ):
        if not isinstance(event, dict):
            continue

        event_player_ids = event.get(
            "player_ids",
            [],
        )

        if isinstance(event_player_ids, str):
            event_player_ids = [
                event_player_ids
            ]

        if not isinstance(event_player_ids, list):
            event_player_ids = []

        event_player_ids = [
            str(player_id)
            for player_id in event_player_ids
            if str(player_id) in player_ids
        ]

        if not event_player_ids:
            event_player_ids = player_ids.copy()

        phase = _phase_number(
            event.get(
                "phase",
                event.get(
                    "phase_id",
                    1,
                ),
            ),
            original_phases,
        )

        phase = max(
            1,
            min(
                len(normalized_phases),
                phase,
            ),
        )

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
                "phase": phase,
                "title": str(
                    event.get(
                        "title",
                        event.get(
                            "name",
                            f"Gebeurtenis {index}",
                        ),
                    )
                ),
                "description": str(
                    event.get(
                        "description",
                        event.get(
                            "details",
                            "Een nieuwe gebeurtenis verandert de situatie.",
                        ),
                    )
                ),
                "delivery": _normalize_delivery(
                    event.get(
                        "delivery",
                        "website",
                    )
                ),
                "release_after_days": max(
                    0,
                    _safe_int(
                        event.get(
                            "release_after_days",
                            0,
                        ),
                        0,
                    ),
                ),
                "player_ids": event_player_ids,
            }
        )

    raw["events"] = normalized_events

    # ========================================================
    # VOTING MOMENTS
    # ========================================================

    original_votes = raw.get(
        "voting_moments",
        [],
    )

    if not isinstance(original_votes, list):
        original_votes = []

    normalized_votes: list[dict[str, Any]] = []

    for index, voting in enumerate(
        original_votes,
        start=1,
    ):
        if not isinstance(voting, dict):
            continue

        phase = _phase_number(
            voting.get(
                "phase",
                voting.get(
                    "phase_id",
                    1,
                ),
            ),
            original_phases,
        )

        phase = max(
            1,
            min(
                len(normalized_phases),
                phase,
            ),
        )

        duration_hours = max(
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
        )

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
                "phase": phase,
                "question": str(
                    voting.get(
                        "question",
                        voting.get(
                            "name",
                            "Wie verdenken jullie?",
                        ),
                    )
                ),
                "release_after_days": max(
                    0,
                    _safe_int(
                        voting.get(
                            "release_after_days",
                            0,
                        ),
                        0,
                    ),
                ),
                "duration_hours": duration_hours,
            }
        )

    minimum_votes = _minimum_votes(
        requested_duration
    )

    # Maak ontbrekende stemmomenten aan.
    while len(normalized_votes) < minimum_votes:
        index = len(normalized_votes) + 1

        phase = min(
            len(normalized_phases),
            max(
                1,
                index,
            ),
        )

        normalized_votes.append(
            {
                "id": f"vote-{index}",
                "phase": phase,
                "question": (
                    "Wie verdenk je op basis van de huidige aanwijzingen?"
                    if index == 1
                    else "Welke speler vertrouw je het minst?"
                ),
                "release_after_days": _default_release_day(
                    phase,
                    requested_duration,
                ),
                "duration_hours": 24,
            }
        )

    raw["voting_moments"] = normalized_votes

    # ========================================================
    # GLOBAL CLUES
    # ========================================================

    normalized_clues: list[dict[str, Any]] = []

    for index, clue in enumerate(
        global_clues_raw,
        start=1,
    ):
        if not isinstance(clue, dict):
            continue

        text = clue.get(
            "text",
            clue.get(
                "description",
                "",
            ),
        )

        text = str(text).strip()

        if not text:
            continue

        owner_player_id = str(
            clue.get(
                "owner_player_id",
                "1",
            )
        )

        if owner_player_id not in player_ids:
            owner_player_id = (
                player_ids[0]
                if player_ids
                else "1"
            )

        release_phase = _phase_number(
            clue.get(
                "release_phase",
                clue.get(
                    "phase",
                    clue.get(
                        "phase_id",
                        1,
                    ),
                ),
            ),
            original_phases,
        )

        release_phase = max(
            1,
            min(
                len(normalized_phases),
                release_phase,
            ),
        )

        supports = clue.get(
            "supports",
            [],
        )

        if isinstance(supports, str):
            supports = [
                supports
            ]

        if not isinstance(supports, list):
            supports = []

        supports = [
            str(item)
            for item in supports
            if str(item).strip()
        ]

        if not supports:
            supports = [
                "solution"
            ]

        dependencies = clue.get(
            "dependencies",
            [],
        )

        if isinstance(dependencies, str):
            dependencies = [
                dependencies
            ]

        if not isinstance(dependencies, list):
            dependencies = []

        clue_type = _normalize_clue_type(
            clue.get(
                "clue_type",
                "direct",
            )
        )

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
                "text": text,
                "clue_type": clue_type,
                "owner_player_id": owner_player_id,
                "release_phase": release_phase,
                "visibility": _normalize_visibility(
                    clue.get(
                        "visibility",
                        "public",
                    )
                ),
                "supports": supports,
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

    # ========================================================
    # CRITICAL FIX:
    # GLOBAL CLUES ARE NOW GUARANTEED.
    # ========================================================

    minimum_global_clues = (
        len(names) * clue_count
    )

    existing_texts = {
        clue["text"]
        for clue in normalized_clues
    }

    # Eerst gebruiken we de player clues die de AI al gaf.
    for player in normalized_players:
        owner = player["player_id"]

        for player_clue_index, text in enumerate(
            player["clues"],
            start=1,
        ):
            if len(normalized_clues) >= minimum_global_clues:
                break

            if text in existing_texts:
                continue

            clue_id = (
                f"player-{owner}-clue-{player_clue_index}"
            )

            normalized_clues.append(
                {
                    "id": clue_id,
                    "text": text,
                    "clue_type": "personal",
                    "owner_player_id": owner,
                    "release_phase": min(
                        player_clue_index,
                        len(normalized_phases),
                    ),
                    "visibility": "private",
                    "supports": [
                        "solution"
                    ],
                    "dependencies": [],
                    "red_herring": False,
                }
            )

            existing_texts.add(text)

    # Als zelfs dat niet genoeg is, maken we veilige fallback clues.
    fallback_counter = 1

    while len(normalized_clues) < minimum_global_clues:

        owner = player_ids[
            (fallback_counter - 1)
            % len(player_ids)
        ]

        text = (
            f"Onderzoeksaanwijzing {fallback_counter}: "
            f"de verklaring van speler {owner} "
            f"bevat mogelijk een detail dat niet overeenkomt "
            f"met de andere beschikbare informatie."
        )

        normalized_clues.append(
            {
                "id": f"fallback-clue-{fallback_counter}",
                "text": text,
                "clue_type": "indirect",
                "owner_player_id": owner,
                "release_phase": min(
                    max(
                        1,
                        fallback_counter,
                    ),
                    len(normalized_phases),
                ),
                "visibility": "private",
                "supports": [
                    "solution"
                ],
                "dependencies": [],
                "red_herring": False,
            }
        )

        fallback_counter += 1

    # Forceer unieke clue IDs.
    seen_clue_ids: set[str] = set()

    for index, clue in enumerate(
        normalized_clues,
        start=1,
    ):
        clue_id = str(
            clue.get(
                "id",
                f"clue-{index}",
            )
        )

        if clue_id in seen_clue_ids:
            clue_id = f"{clue_id}-{index}"

        seen_clue_ids.add(clue_id)
        clue["id"] = clue_id

    raw["clues"] = normalized_clues

    # ========================================================
    # CANONICAL TOP-LEVEL VALUES
    # ========================================================

    # De geselecteerde instellingen mogen niet door de AI worden
    # veranderd.
    raw["game_id"] = raw.get(
        "game_id",
        "",
    )

    raw["game_name"] = raw.get(
        "game_name",
        "",
    )

    raw["difficulty"] = raw.get(
        "difficulty",
        "medium",
    )

    raw["duration"] = raw.get(
        "duration",
        requested_duration,
    )

    return raw


# ============================================================
# HELPERS
# ============================================================


def _safe_int(
    value: Any,
    default: int | None,
) -> int | None:
    try:
        if value is None:
            return default

        if isinstance(value, bool):
            return default

        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def _string_list(
    value: Any,
) -> list[str]:

    if isinstance(value, str):
        value = [
            value
        ]

    if not isinstance(value, list):
        return [
            "Onderzoek de situatie."
        ]

    result = [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]

    return (
        result
        or [
            "Onderzoek de situatie."
        ]
    )


def _normalize_metric(
    value: Any,
) -> str:

    value = str(
        value
    ).lower().strip()

    mapping = {
        "clues": "clue_found",
        "clue": "clue_found",
        "find_clue": "clue_found",
        "find_clues": "clue_found",
        "votes": "vote_received",
        "vote": "vote_received",
        "suspected": "top_suspect",
        "top_suspect": "top_suspect",
        "avoid_suspicion": "not_top_suspect",
        "not_suspected": "not_top_suspect",
        "theory": "theory_adopted",
        "change_vote": "vote_change",
        "change_votes": "vote_change",
        "manual": "manual_review",
    }

    value = mapping.get(
        value,
        value,
    )

    allowed = {
        "vote_received",
        "top_suspect",
        "not_top_suspect",
        "mutual_suspicion",
        "theory_adopted",
        "vote_change",
        "clue_found",
        "manual_review",
    }

    return (
        value
        if value in allowed
        else "manual_review"
    )


def _normalize_clue_type(
    value: Any,
) -> str:

    value = str(
        value
    ).lower().strip()

    mapping = {
        "clue": "direct",
        "evidence": "direct",
        "hint": "indirect",
        "relation": "relational",
        "relationships": "relational",
        "time": "timeline",
        "place": "location",
        "item": "object",
        "person": "witness",
        "proof": "confirming",
        "important": "crucial",
        "false": "red_herring",
        "personal_clue": "personal",
    }

    value = mapping.get(
        value,
        value,
    )

    allowed = {
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

    return (
        value
        if value in allowed
        else "direct"
    )


def _normalize_delivery(
    value: Any,
) -> str:

    value = str(
        value
    ).lower().strip()

    mapping = {
        "web": "website",
        "site": "website",
        "mail": "email",
        "physical": "physical_clue",
        "physical clue": "physical_clue",
        "qr": "qr_code",
        "qr code": "qr_code",
        "document": "printed_document",
        "print": "printed_document",
        "printed": "printed_document",
    }

    value = mapping.get(
        value,
        value,
    )

    allowed = {
        "website",
        "email",
        "physical_clue",
        "qr_code",
        "whatsapp",
        "printed_document",
    }

    return (
        value
        if value in allowed
        else "website"
    )


def _normalize_visibility(
    value: Any,
) -> str:

    value = str(
        value
    ).lower().strip()

    mapping = {
        "shared": "shareable",
        "everyone": "public",
        "all": "public",
        "secret": "private",
        "hidden": "private",
    }

    value = mapping.get(
        value,
        value,
    )

    allowed = {
        "public",
        "private",
        "shareable",
    }

    return (
        value
        if value in allowed
        else "public"
    )


def _minimum_phases(
    duration: str,
) -> int:

    if duration == "1_maand":
        return 5

    if duration in {
        "2_weken",
        "3_weken",
    }:
        return 3

    return 1


def _minimum_votes(
    duration: str,
) -> int:

    if duration == "1_maand":
        return 3

    if duration in {
        "2_weken",
        "3_weken",
    }:
        return 2

    return 1


def _default_phase_name(
    number: int,
) -> str:

    names = {
        1: "Start",
        2: "Onderzoek",
        3: "Verdieping",
        4: "Confrontatie",
        5: "Ontknoping",
    }

    return names.get(
        number,
        f"Fase {number}",
    )


def _default_phase_purpose(
    number: int,
) -> str:

    purposes = {
        1: "Verzamel de eerste informatie.",
        2: "Onderzoek tegenstrijdigheden en mogelijke motieven.",
        3: "Leg verbanden tussen de verschillende aanwijzingen.",
        4: "Confronteer theorieën en verdachten.",
        5: "Los het mysterie definitief op.",
    }

    return purposes.get(
        number,
        "Onderzoek nieuwe informatie.",
    )


def _default_phase_question(
    number: int,
) -> str:

    questions = {
        1: "Wat is er werkelijk gebeurd?",
        2: "Welke verklaringen kloppen niet?",
        3: "Wie heeft het meeste te verbergen?",
        4: "Welke theorie verklaart alle aanwijzingen?",
        5: "Wie is uiteindelijk verantwoordelijk?",
    }

    return questions.get(
        number,
        "Wat is de waarheid?",
    )


def _default_release_day(
    phase: int,
    duration: str,
) -> int:

    if duration == "avond":
        return 0

    if duration == "1_week":
        return max(
            0,
            (phase - 1) * 2,
        )

    if duration == "2_weken":
        return max(
            0,
            (phase - 1) * 4,
        )

    if duration == "3_weken":
        return max(
            0,
            (phase - 1) * 5,
        )

    if duration == "1_maand":
        return max(
            0,
            (phase - 1) * 7,
        )

    return 0


# ============================================================
# FINAL VALIDATION
# ============================================================


def _validate_generation(
    generated: GeneratedGame,
    game: dict[str, Any],
    names: list[str],
    clue_count: int,
    requested_difficulty: str,
    requested_duration: str,
) -> None:

    clue_count = max(
        2,
        int(clue_count),
    )

    # ========================================================
    # CANONICAL GAME
    # ========================================================

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
        raise ValueError(
            "solution cannot be empty"
        )

    if not generated.truth_model.strip():
        raise ValueError(
            "truth_model cannot be empty"
        )

    # ========================================================
    # PLAYERS
    # ========================================================

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
        expected_id = str(
            index + 1
        )

        if player.player_id != expected_id:
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

        # Dit was de fout die je nu kreeg.
        if len(player.clues) < clue_count:
            raise ValueError(
                f"player {index + 1} has insufficient clues: "
                f"expected {clue_count}, "
                f"received {len(player.clues)}"
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

            if not (
                1
                <= objective.activate_phase
                <= len(generated.phases)
            ):
                raise ValueError(
                    f"objective {objective.id} references "
                    f"invalid phase {objective.activate_phase}"
                )

    # ========================================================
    # SABOTEURS
    # ========================================================

    actual_saboteurs = sum(
        1
        for player in generated.players
        if player.is_saboteur
    )

    if actual_saboteurs < 1:
        raise ValueError(
            "at least one saboteur is required"
        )

    if generated.saboteur_count != actual_saboteurs:
        raise ValueError(
            "saboteur_count does not match player assignments"
        )

    # ========================================================
    # PHASES
    # ========================================================

    minimum_phases = _minimum_phases(
        requested_duration
    )

    if len(generated.phases) < minimum_phases:
        raise ValueError(
            f"duration requires at least {minimum_phases} phases"
        )

    phase_numbers = {
        phase.number
        for phase in generated.phases
    }

    if len(phase_numbers) != len(
        generated.phases
    ):
        raise ValueError(
            "phase numbers must be unique"
        )

    expected_phase_numbers = set(
        range(
            1,
            len(generated.phases) + 1,
        )
    )

    if phase_numbers != expected_phase_numbers:
        raise ValueError(
            "phase numbers must be sequential starting at 1"
        )

    # ========================================================
    # VOTING
    # ========================================================

    minimum_votes = _minimum_votes(
        requested_duration
    )

    if len(generated.voting_moments) < minimum_votes:
        raise ValueError(
            f"duration requires at least {minimum_votes} voting moments"
        )

    voting_ids = [
        voting.id
        for voting in generated.voting_moments
    ]

    if len(voting_ids) != len(
        set(voting_ids)
    ):
        raise ValueError(
            "voting moment IDs must be unique"
        )

    for voting in generated.voting_moments:
        if voting.phase not in phase_numbers:
            raise ValueError(
                f"voting moment {voting.id} references "
                f"unknown phase {voting.phase}"
            )

    # ========================================================
    # EVENTS
    # ========================================================

    event_ids = [
        event.id
        for event in generated.events
    ]

    if len(event_ids) != len(
        set(event_ids)
    ):
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

    # ========================================================
    # GLOBAL CLUES
    # ========================================================

    clue_ids = [
        clue.id
        for clue in generated.clues
    ]

    if len(clue_ids) != len(
        set(clue_ids)
    ):
        raise ValueError(
            "clue IDs must be unique"
        )

    minimum_global_clues = (
        len(names) * clue_count
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