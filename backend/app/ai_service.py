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


ALLOWED_OBJECTIVE_METRICS = {
    "vote_received",
    "top_suspect",
    "not_top_suspect",
    "mutual_suspicion",
    "theory_adopted",
    "vote_change",
    "clue_found",
    "manual_review",
}


ALLOWED_CLUE_TYPES = {
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


ALLOWED_DELIVERIES = {
    "website",
    "email",
    "physical_clue",
    "qr_code",
    "whatsapp",
    "printed_document",
}


ALLOWED_VISIBILITIES = {
    "public",
    "private",
    "shareable",
}


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
    visibility: Literal[
        "public",
        "private",
        "shareable",
    ]
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
    personal_objectives: list[GeneratedObjective] = Field(
        min_length=1
    )
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
    duration_hours: int = Field(
        ge=1,
        le=168,
    )


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
    difficulty: Literal[
        "easy",
        "medium",
        "hard",
    ]
    duration: Duration
    saboteur_count: int = Field(ge=1)
    team_win_condition: str
    individual_win_condition: str
    saboteur_win_condition: str
    truth_model: str
    phases: list[GeneratedPhase] = Field(min_length=1)
    events: list[GeneratedEvent] = Field(default_factory=list)
    voting_moments: list[GeneratedVotingMoment] = Field(
        min_length=1
    )
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
                "AI_PROVIDER_NOT_CONFIGURED: "
                "configureer AI_API_KEY voor echte gamegeneratie."
            )

        if not names:
            raise ValueError(
                "AI_GAME_GENERATION_FAILED: minimaal één speler vereist."
            )

        clue_count = max(2, int(clue_count))

        prompt = {
            "game_id": game["id"],
            "game_name": game["name"],
            "game_rules": game.get("rules", []),
            "available_roles": [
                role["name"]
                for role in game.get("roles", [])
            ],
            "players": [
                {
                    "player_id": str(index + 1),
                    "name": name,
                }
                for index, name in enumerate(names)
            ],
            "theme": game.get("theme", {}),
            "objective": game.get(
                "goal",
                "Voltooi het spel.",
            ),
            "difficulty": difficulty,
            "duration": duration,
            "clue_count_per_player": clue_count,
            "minimum_global_clues": len(names) * clue_count,
            "language": "Nederlands",
        }

        system_prompt = """
You are a professional tabletop game designer.

Return ONLY one valid JSON object.
Never return markdown.
Never return code fences.

STRICT SCHEMA RULES:

- player_id MUST be a string.
- Player IDs MUST be sequential: "1", "2", "3", etc.
- Generate exactly one player per requested name.
- Preserve the requested player names exactly.
- role MUST come from available_roles.
- relationships MUST be an array of strings.
- personal_objectives MUST be an array of objects.
- objective metric MUST be one of:
  vote_received,
  top_suspect,
  not_top_suspect,
  mutual_suspicion,
  theory_adopted,
  vote_change,
  clue_found,
  manual_review.
- activate_phase MUST be an integer.
- phases MUST use integer number values.
- events MUST use integer phase values.
- voting_moments MUST use integer phase values.
- clues MUST use integer release_phase values.
- Never use phase names as phase references.
- Use "id", never phase_id/event_id/voting_id/clue_id.
- Event title field is "title".
- Voting question field is "question".
- Clue text field is "text".
- clue_type MUST be one of:
  direct,
  indirect,
  relational,
  timeline,
  alibi,
  location,
  object,
  witness,
  confirming,
  crucial,
  red_herring,
  personal.
- visibility MUST be:
  public,
  private,
  shareable.
- Every player MUST have at least the requested number of clues.
- Every global clue MUST have:
  id,
  text,
  clue_type,
  owner_player_id,
  release_phase,
  visibility,
  supports,
  dependencies,
  red_herring.
- supports MUST contain at least one string.
- Every event MUST contain at least one player_id.
- Every phase MUST contain at least one objective.
- All player-facing text MUST be Dutch.
"""

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
                                "minimum_player_clues": clue_count,
                                "minimum_global_clues": (
                                    len(names) * clue_count
                                ),
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
            "Authorization": (
                f"Bearer {settings.ai_api_key}"
            ),
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                async with httpx.AsyncClient(
                    timeout=60
                ) as client:
                    response = await client.post(
                        (
                            f"{settings.ai_base_url.rstrip('/')}"
                            "/chat/completions"
                        ),
                        json=body,
                        headers=headers,
                    )

                    response.raise_for_status()

                    response_data = response.json()

                    content = (
                        response_data
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content")
                    )

                    if not isinstance(content, str):
                        raise ValueError(
                            "AI returned no textual JSON content."
                        )

                    raw = json.loads(content)

                    if not isinstance(raw, dict):
                        raise ValueError(
                            "AI output must be a JSON object."
                        )

                    raw = _normalize_generation(
                        raw,
                        names=names,
                        game=game,
                        clue_count=clue_count,
                        difficulty=difficulty,
                        duration=duration,
                    )

                    generated = (
                        GeneratedGame.model_validate(raw)
                    )

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
                    "AI generation validation failed "
                    "on attempt %s: %s",
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
                json.JSONDecodeError,
            ) as exc:
                logger.exception(
                    "AI game generation failed "
                    "on attempt %s",
                    attempt,
                )
                last_error = exc

            if attempt < 3:
                await asyncio.sleep(0.75 * attempt)

        raise RuntimeError(
            f"AI_GAME_GENERATION_FAILED: {last_error}"
        ) from last_error


def _normalize_generation(
    raw: dict[str, Any],
    *,
    names: list[str],
    game: dict[str, Any],
    clue_count: int,
    difficulty: str,
    duration: str,
) -> dict[str, Any]:
    """
    Convert flexible AI JSON into the exact internal schema.

    This function is intentionally defensive. AI output is treated
    as untrusted input and normalized before Pydantic validation.
    """

    if not isinstance(raw, dict):
        raise ValueError(
            "AI output must be a JSON object."
        )

    player_ids = [
        str(index + 1)
        for index in range(len(names))
    ]

    phases = _normalize_phases(
        raw.get("phases"),
        duration,
    )

    phase_numbers = {
        phase["number"]
        for phase in phases
    }

    # ---------------------------------------------------------
    # PLAYERS
    # ---------------------------------------------------------

    raw_players = raw.get("players")

    if not isinstance(raw_players, list):
        raw_players = []

    players_by_id: dict[str, dict[str, Any]] = {}

    for index, player in enumerate(raw_players):
        if not isinstance(player, dict):
            continue

        requested_id = str(
            player.get(
                "player_id",
                index + 1,
            )
        )

        if requested_id not in player_ids:
            requested_id = (
                str(index + 1)
                if index < len(names)
                else ""
            )

        if requested_id:
            players_by_id[requested_id] = player

    normalized_players = []

    for index, player_id in enumerate(player_ids):
        player = players_by_id.get(
            player_id,
            {},
        )

        player_name = names[index]

        relationships = _normalize_string_list(
            player.get("relationships"),
        )

        personal_objectives = _normalize_objectives(
            player.get("personal_objectives"),
            player_id,
            phases,
        )

        if not personal_objectives:
            personal_objectives = [
                {
                    "id": (
                        f"{player_id}-objective-1"
                    ),
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
            ]

        raw_player_clues = _extract_clue_texts(
            player.get("clues")
        )

        normalized_players.append(
            {
                "player_id": player_id,
                "name": player_name,
                "role": str(
                    player.get(
                        "role",
                        _default_role(game),
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
                "personal_objectives": personal_objectives,
                "secret_information": str(
                    player.get(
                        "secret_information",
                        player.get(
                            "secret",
                            "",
                        ),
                    )
                ),
                "clues": raw_player_clues,
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

    # ---------------------------------------------------------
    # GLOBAL CLUES
    # ---------------------------------------------------------

    normalized_clues = _normalize_global_clues(
        raw.get("clues"),
        names=names,
        phases=phases,
        clue_count=clue_count,
        player_data=normalized_players,
    )

    # Ensure every player has enough clue text.
    clue_texts_by_player: dict[str, list[str]] = {
        player_id: []
        for player_id in player_ids
    }

    for clue in normalized_clues:
        owner = clue["owner_player_id"]

        if owner in clue_texts_by_player:
            clue_texts_by_player[owner].append(
                clue["text"]
            )

    # Use globally generated clues as fallback,
    # then create deterministic clues if necessary.
    fallback_texts = [
        clue["text"]
        for clue in normalized_clues
        if clue.get("text")
    ]

    for player in normalized_players:
        player_id = player["player_id"]
        clues = list(player["clues"])

        for text in clue_texts_by_player.get(
            player_id,
            [],
        ):
            if text not in clues:
                clues.append(text)

        for text in fallback_texts:
            if len(clues) >= clue_count:
                break

            if text not in clues:
                clues.append(text)

        while len(clues) < clue_count:
            clues.append(
                _fallback_clue_text(
                    player_id,
                    len(clues) + 1,
                )
            )

        player["clues"] = clues[:max(2, clue_count)]

    # ---------------------------------------------------------
    # EVENTS
    # ---------------------------------------------------------

    normalized_events = _normalize_events(
        raw.get("events"),
        phases,
        player_ids,
    )

    # ---------------------------------------------------------
    # VOTING
    # ---------------------------------------------------------

    normalized_votes = _normalize_votes(
        raw.get("voting_moments"),
        phases,
        duration,
    )

    # ---------------------------------------------------------
    # SABOTEUR COUNT
    # ---------------------------------------------------------

    saboteur_count = sum(
        1
        for player in normalized_players
        if player["is_saboteur"]
    )

    if saboteur_count < 1:
        # Make player 2 the default saboteur if possible.
        saboteur_index = (
            1
            if len(normalized_players) > 1
            else 0
        )

        normalized_players[
            saboteur_index
        ]["is_saboteur"] = True

        saboteur_count = 1

    # ---------------------------------------------------------
    # TOP-LEVEL GAME
    # ---------------------------------------------------------

    raw["game_id"] = game["id"]
    raw["game_name"] = game["name"]

    raw["title"] = str(
        raw.get(
            "title",
            game["name"],
        )
    )

    raw["story"] = str(
        raw.get(
            "story",
            "Een spannend spel waarin de spelers "
            "moeten samenwerken terwijl niet iedereen "
            "dezelfde agenda heeft.",
        )
    )

    raw["objective"] = str(
        raw.get(
            "objective",
            game.get(
                "goal",
                "Voltooi het spel.",
            ),
        )
    )

    raw["rules"] = _string_list(
        raw.get("rules")
    )

    raw["players"] = normalized_players

    raw["solution"] = str(
        raw.get(
            "solution",
            "De waarheid moet door de spelers "
            "worden ontdekt.",
        )
    )

    raw["difficulty"] = difficulty
    raw["duration"] = duration

    raw["saboteur_count"] = saboteur_count

    raw["team_win_condition"] = str(
        raw.get(
            "team_win_condition",
            "Voltooi het gezamenlijke doel.",
        )
    )

    raw["individual_win_condition"] = str(
        raw.get(
            "individual_win_condition",
            "Bereik je persoonlijke doel.",
        )
    )

    raw["saboteur_win_condition"] = str(
        raw.get(
            "saboteur_win_condition",
            "Saboteer het team zonder ontmaskerd te worden.",
        )
    )

    raw["truth_model"] = str(
        raw.get(
            "truth_model",
            "De oplossing wordt bepaald door de "
            "geheime informatie en clues.",
        )
    )

    raw["phases"] = phases
    raw["events"] = normalized_events
    raw["voting_moments"] = normalized_votes
    raw["clues"] = normalized_clues

    return raw


def _normalize_phases(
    raw_phases: Any,
    duration: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_phases, list):
        raw_phases = []

    minimum = _minimum_phases(duration)

    phases: list[dict[str, Any]] = []

    for index, phase in enumerate(
        raw_phases,
        start=1,
    ):
        if not isinstance(phase, dict):
            continue

        name = str(
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

        phases.append(
            {
                "number": index,
                "name": name,
                "purpose": str(
                    phase.get(
                        "purpose",
                        phase.get(
                            "description",
                            "Onderzoek de situatie.",
                        ),
                    )
                ),
                "open_question": str(
                    phase.get(
                        "open_question",
                        phase.get(
                            "question",
                            "Wat is hier echt aan de hand?",
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
                            [
                                "Verzamel informatie."
                            ],
                        ),
                    )
                ),
            }
        )

    while len(phases) < minimum:
        index = len(phases) + 1

        phases.append(
            {
                "number": index,
                "name": _default_phase_name(index),
                "purpose": _default_phase_purpose(index),
                "open_question": (
                    "Welke informatie ontbreekt nog?"
                ),
                "release_after_days": (
                    _default_phase_day(
                        index,
                        duration,
                    )
                ),
                "objectives": [
                    "Verzamel informatie.",
                    "Werk samen met de andere spelers.",
                ],
            }
        )

    return phases


def _normalize_global_clues(
    raw_clues: Any,
    *,
    names: list[str],
    phases: list[dict[str, Any]],
    clue_count: int,
    player_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_clues, list):
        raw_clues = []

    normalized: list[dict[str, Any]] = []

    for index, clue in enumerate(
        raw_clues,
        start=1,
    ):
        # AI kan een clue als string teruggeven.
        if isinstance(clue, str):
            text = clue.strip()

            if not text:
                continue

            owner = (
                str(
                    ((index - 1) % len(names)) + 1
                )
                if names
                else "1"
            )

            normalized.append(
                _make_clue(
                    clue_id=f"clue-{index}",
                    text=text,
                    owner_player_id=owner,
                    phase=1,
                    clue_type="direct",
                    visibility="public",
                    supports=["solution"],
                )
            )

            continue

        if not isinstance(clue, dict):
            continue

        text = str(
            clue.get(
                "text",
                clue.get(
                    "description",
                    clue.get(
                        "clue",
                        "",
                    ),
                ),
            )
        ).strip()

        if not text:
            continue

        owner = str(
            clue.get(
                "owner_player_id",
                clue.get(
                    "owner",
                    "1",
                ),
            )
        )

        if not owner.isdigit():
            owner = "1"

        if int(owner) < 1 or int(owner) > len(names):
            owner = "1"

        phase = _phase_number(
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
            phases,
        )

        clue_type = _normalize_clue_type(
            clue.get(
                "clue_type",
                "direct",
            )
        )

        supports = _normalize_string_list(
            clue.get("supports")
        )

        if not supports:
            supports = ["solution"]

        dependencies = _normalize_string_list(
            clue.get("dependencies")
        )

        normalized.append(
            _make_clue(
                clue_id=str(
                    clue.get(
                        "id",
                        clue.get(
                            "clue_id",
                            f"clue-{index}",
                        ),
                    )
                ),
                text=text,
                owner_player_id=owner,
                phase=phase,
                clue_type=clue_type,
                visibility=_normalize_visibility(
                    clue.get(
                        "visibility",
                        "public",
                    )
                ),
                supports=supports,
                dependencies=dependencies,
                red_herring=bool(
                    clue.get(
                        "red_herring",
                        False,
                    )
                ),
            )
        )

    # ---------------------------------------------------------
    # DEDUPE IDs
    # ---------------------------------------------------------

    seen_ids: set[str] = set()

    for clue in normalized:
        original_id = clue["id"]
        clue_id = original_id
        suffix = 2

        while clue_id in seen_ids:
            clue_id = (
                f"{original_id}-{suffix}"
            )
            suffix += 1

        clue["id"] = clue_id
        seen_ids.add(clue_id)

    # ---------------------------------------------------------
    # GUARANTEE ENOUGH GLOBAL CLUES
    #
    # The old version checked for 21 clues but never created
    # them. This is the actual fix.
    # ---------------------------------------------------------

    minimum_global = len(names) * clue_count

    source_clues = list(normalized)

    while len(normalized) < minimum_global:
        index = len(normalized) + 1

        owner = (
            ((index - 1) % len(names)) + 1
            if names
            else 1
        )

        source = (
            source_clues[
                (index - 1) % len(source_clues)
            ]
            if source_clues
            else None
        )

        if source:
            text = source["text"]
            clue_type = source["clue_type"]
            visibility = source["visibility"]
            supports = list(
                source["supports"]
            )
        else:
            text = _fallback_clue_text(
                str(owner),
                ((index - 1) % clue_count) + 1,
            )
            clue_type = "direct"
            visibility = "public"
            supports = ["solution"]

        normalized.append(
            _make_clue(
                clue_id=f"clue-{index}",
                text=text,
                owner_player_id=str(owner),
                phase=1,
                clue_type=clue_type,
                visibility=visibility,
                supports=supports,
            )
        )

    # ---------------------------------------------------------
    # Make sure every generated clue has a valid owner.
    # ---------------------------------------------------------

    valid_ids = {
        str(index + 1)
        for index in range(len(names))
    }

    for clue in normalized:
        if clue["owner_player_id"] not in valid_ids:
            clue["owner_player_id"] = "1"

        if clue["release_phase"] not in {
            phase["number"]
            for phase in phases
        }:
            clue["release_phase"] = 1

    return normalized


def _normalize_events(
    raw_events: Any,
    phases: list[dict[str, Any]],
    player_ids: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list):
        raw_events = []

    result = []

    for index, event in enumerate(
        raw_events,
        start=1,
    ):
        if not isinstance(event, dict):
            continue

        ids = _normalize_string_list(
            event.get("player_ids")
        )

        ids = [
            player_id
            for player_id in ids
            if player_id in player_ids
        ]

        if not ids:
            ids = [
                player_ids[
                    (index - 1) % len(player_ids)
                ]
            ]

        result.append(
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
                            "Er gebeurt iets belangrijks.",
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
                "player_ids": ids,
            }
        )

    return result


def _normalize_votes(
    raw_votes: Any,
    phases: list[dict[str, Any]],
    duration: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw_votes, list):
        raw_votes = []

    result = []

    for index, voting in enumerate(
        raw_votes,
        start=1,
    ):
        if not isinstance(voting, dict):
            continue

        result.append(
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

    minimum_votes = _minimum_votes(duration)

    while len(result) < minimum_votes:
        index = len(result) + 1

        phase = min(
            index,
            len(phases),
        )

        result.append(
            {
                "id": f"vote-{index}",
                "phase": phase,
                "question": (
                    "Wie verdenken jullie op dit moment?"
                    if index == 1
                    else "Is jullie verdenking veranderd?"
                ),
                "release_after_days": (
                    phases[phase - 1][
                        "release_after_days"
                    ]
                ),
                "duration_hours": 24,
            }
        )

    return result


def _normalize_objectives(
    raw_objectives: Any,
    player_id: str,
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(raw_objectives, dict):
        raw_objectives = [raw_objectives]

    if not isinstance(raw_objectives, list):
        return []

    result = []

    for index, objective in enumerate(
        raw_objectives,
        start=1,
    ):
        if not isinstance(objective, dict):
            continue

        metric = str(
            objective.get(
                "metric",
                "manual_review",
            )
        ).lower().strip()

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
            metric,
            metric,
        )

        if metric not in ALLOWED_OBJECTIVE_METRICS:
            metric = "manual_review"

        activate_phase = _phase_number(
            objective.get(
                "activate_phase",
                1,
            ),
            phases,
        )

        result.append(
            {
                "id": str(
                    objective.get(
                        "id",
                        (
                            f"{player_id}"
                            f"-objective-{index}"
                        ),
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
                        objective[
                            "target_player_id"
                        ]
                    )
                    if objective.get(
                        "target_player_id"
                    )
                    is not None
                    else None
                ),
                "target_value": (
                    _safe_int(
                        objective[
                            "target_value"
                        ],
                        None,
                    )
                    if objective.get(
                        "target_value"
                    )
                    is not None
                    else None
                ),
                "activate_phase": activate_phase,
            }
        )

    return result


def _extract_clue_texts(
    value: Any,
) -> list[str]:
    """
    Converts all known AI clue formats to list[str].

    Handles:
      "Een clue"
      {"text": "Een clue"}
      {"description": "Een clue"}
      [{"text": "..."}]
    """

    if value is None:
        return []

    if isinstance(value, str):
        return (
            [value.strip()]
            if value.strip()
            else []
        )

    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        if isinstance(item, str):
            text = item.strip()

        elif isinstance(item, dict):
            text = str(
                item.get(
                    "text",
                    item.get(
                        "description",
                        item.get(
                            "clue",
                            "",
                        ),
                    ),
                )
            ).strip()

        else:
            continue

        if text and text not in result:
            result.append(text)

    return result


def _make_clue(
    *,
    clue_id: str,
    text: str,
    owner_player_id: str,
    phase: int,
    clue_type: str,
    visibility: str,
    supports: list[str],
    dependencies: list[str] | None = None,
    red_herring: bool = False,
) -> dict[str, Any]:
    return {
        "id": clue_id,
        "text": text,
        "clue_type": clue_type,
        "owner_player_id": owner_player_id,
        "release_phase": max(1, phase),
        "visibility": visibility,
        "supports": supports or ["solution"],
        "dependencies": (
            dependencies
            if dependencies is not None
            else []
        ),
        "red_herring": red_herring,
    }


def _normalize_clue_type(
    value: Any,
) -> str:
    value = str(
        value or "direct"
    ).lower().strip()

    mapping = {
        "information": "direct",
        "info": "direct",
        "fact": "direct",
        "hint": "indirect",
        "relationship": "relational",
        "relation": "relational",
        "time": "timeline",
        "alibi_clue": "alibi",
        "place": "location",
        "item": "object",
        "person": "witness",
        "confirmation": "confirming",
        "important": "crucial",
        "false": "red_herring",
        "personal_clue": "personal",
    }

    value = mapping.get(
        value,
        value,
    )

    return (
        value
        if value in ALLOWED_CLUE_TYPES
        else "direct"
    )


def _normalize_delivery(
    value: Any,
) -> str:
    value = str(
        value or "website"
    ).lower().strip()

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

    value = mapping.get(
        value,
        value,
    )

    return (
        value
        if value in ALLOWED_DELIVERIES
        else "website"
    )


def _normalize_visibility(
    value: Any,
) -> str:
    value = str(
        value or "public"
    ).lower().strip()

    mapping = {
        "shared": "shareable",
        "everyone": "public",
        "all": "public",
        "secret": "private",
        "shared_with_players": "shareable",
    }

    value = mapping.get(
        value,
        value,
    )

    return (
        value
        if value in ALLOWED_VISIBILITIES
        else "public"
    )


def _normalize_string_list(
    value: Any,
) -> list[str]:
    if isinstance(value, str):
        return (
            [value.strip()]
            if value.strip()
            else []
        )

    if not isinstance(value, list):
        return []

    result = []

    for item in value:
        if isinstance(item, dict):
            # Relationships occasionally come back as
            # {"player": "...", "relationship": "..."}.
            if "text" in item:
                item = item["text"]
            elif "description" in item:
                item = item["description"]
            else:
                item = ", ".join(
                    f"{key}: {value}"
                    for key, value in item.items()
                )

        text = str(item).strip()

        if text and text not in result:
            result.append(text)

    return result


def _string_list(
    value: Any,
) -> list[str]:
    result = _normalize_string_list(value)

    return (
        result
        if result
        else ["Onderzoek de situatie."]
    )


def _phase_number(
    value: Any,
    phases: list[dict[str, Any]],
) -> int:
    if isinstance(value, bool):
        return 1

    if isinstance(value, int):
        return _clamp_phase(
            value,
            phases,
        )

    if isinstance(value, float):
        return _clamp_phase(
            int(value),
            phases,
        )

    if isinstance(value, str):
        clean = value.lower().strip()

        if clean.isdigit():
            return _clamp_phase(
                int(clean),
                phases,
            )

        for phase in phases:
            if clean in {
                str(
                    phase.get(
                        "name",
                        ""
                    )
                ).lower().strip(),
            }:
                return phase["number"]

    return 1


def _clamp_phase(
    value: int,
    phases: list[dict[str, Any]],
) -> int:
    if not phases:
        return 1

    numbers = [
        phase["number"]
        for phase in phases
    ]

    minimum = min(numbers)
    maximum = max(numbers)

    return max(
        minimum,
        min(maximum, value),
    )


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


def _default_role(
    game: dict[str, Any],
) -> str:
    roles = game.get("roles", [])

    if roles:
        return str(
            roles[0].get(
                "name",
                "Speler",
            )
        )

    return "Speler"


def _fallback_clue_text(
    player_id: str,
    clue_number: int,
) -> str:
    fallback = [
        "Er ontbreekt nog belangrijke informatie over het plan.",
        "Iemand in de groep weet meer dan hij of zij vertelt.",
        "Een detail uit de gebeurtenissen lijkt niet helemaal te kloppen.",
        "De timing van een belangrijke gebeurtenis roept vragen op.",
        "Niet alle informatie is met iedereen gedeeld.",
    ]

    return fallback[
        (int(player_id) + clue_number - 2)
        % len(fallback)
    ]


def _default_phase_name(
    number: int,
) -> str:
    names = {
        1: "De voorbereiding",
        2: "Het onderzoek",
        3: "De confrontatie",
        4: "De onthulling",
        5: "De finale",
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
        2: "Leg verbanden tussen de clues.",
        3: "Test theorieën en verdenkingen.",
        4: "Breng tegenstrijdigheden aan het licht.",
        5: "Los het mysterie definitief op.",
    }

    return purposes.get(
        number,
        "Onderzoek de situatie.",
    )


def _default_phase_day(
    number: int,
    duration: str,
) -> int:
    if duration == "avond":
        return 0

    if duration == "1_week":
        return min(
            number - 1,
            6,
        )

    if duration == "2_weken":
        return min(
            (number - 1) * 3,
            13,
        )

    if duration == "3_weken":
        return min(
            (number - 1) * 4,
            20,
        )

    return min(
        (number - 1) * 6,
        30,
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

    if duration == "1_week":
        return 2

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
            f"expected difficulty "
            f"{requested_difficulty}, "
            f"received {generated.difficulty}"
        )

    if generated.duration != requested_duration:
        raise ValueError(
            f"expected duration "
            f"{requested_duration}, "
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
            "player_id values must be unique "
            "and sequential"
        )

    role_names = {
        role["name"]
        for role in game.get("roles", [])
    }

    for index, player in enumerate(
        generated.players
    ):
        if player.player_id != str(index + 1):
            raise ValueError(
                f"player {index + 1} "
                f"has invalid player_id"
            )

        if player.name != names[index]:
            raise ValueError(
                f"player {index + 1} "
                f"has invalid name"
            )

        if role_names and player.role not in role_names:
            raise ValueError(
                f"player {index + 1} "
                f"has invalid role: {player.role}"
            )

        if len(player.clues) < max(
            2,
            clue_count,
        ):
            raise ValueError(
                f"player {index + 1} "
                f"has insufficient clues"
            )

        if not player.personal_objectives:
            raise ValueError(
                f"player {index + 1} "
                f"has no personal objective"
            )

        for objective in player.personal_objectives:
            if (
                objective.owner_player_id
                != player.player_id
            ):
                raise ValueError(
                    f"objective {objective.id} "
                    f"belongs to "
                    f"{objective.owner_player_id}, "
                    f"but is assigned to "
                    f"{player.player_id}"
                )

            if objective.activate_phase not in {
                phase.number
                for phase in generated.phases
            }:
                raise ValueError(
                    f"objective {objective.id} "
                    f"references unknown phase "
                    f"{objective.activate_phase}"
                )

    actual_saboteurs = sum(
        1
        for player in generated.players
        if player.is_saboteur
    )

    if generated.saboteur_count != actual_saboteurs:
        raise ValueError(
            "saboteur_count does not match "
            "player assignments"
        )

    if actual_saboteurs < 1:
        raise ValueError(
            "at least one saboteur is required"
        )

    minimum_phases = _minimum_phases(
        requested_duration
    )

    minimum_votes = _minimum_votes(
        requested_duration
    )

    if len(generated.phases) < minimum_phases:
        raise ValueError(
            f"duration requires at least "
            f"{minimum_phases} phases"
        )

    if len(generated.voting_moments) < minimum_votes:
        raise ValueError(
            f"duration requires at least "
            f"{minimum_votes} voting moments"
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
                f"voting moment {voting.id} "
                f"references unknown phase "
                f"{voting.phase}"
            )

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
                f"event {event.id} "
                f"references unknown phase "
                f"{event.phase}"
            )

        for player_id in event.player_ids:
            if player_id not in actual_player_ids:
                raise ValueError(
                    f"event {event.id} "
                    f"references unknown player "
                    f"{player_id}"
                )

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
        len(names) * max(
            2,
            clue_count,
        )
    )

    if len(generated.clues) < minimum_global_clues:
        raise ValueError(
            f"expected at least "
            f"{minimum_global_clues} global clues, "
            f"received {len(generated.clues)}"
        )

    for clue in generated.clues:
        if clue.owner_player_id not in actual_player_ids:
            raise ValueError(
                f"clue {clue.id} "
                f"references unknown owner "
                f"{clue.owner_player_id}"
            )

        if clue.release_phase not in phase_numbers:
            raise ValueError(
                f"clue {clue.id} "
                f"references unknown phase "
                f"{clue.release_phase}"
            )

        if not clue.text.strip():
            raise ValueError(
                f"clue {clue.id} "
                f"has empty text"
            )

        if not clue.supports:
            raise ValueError(
                f"clue {clue.id} "
                f"has no supports"
            )

        for dependency in clue.dependencies:
            if dependency not in clue_ids:
                raise ValueError(
                    f"clue {clue.id} "
                    f"references unknown "
                    f"dependency {dependency}"
                )


ai_service = AIService()