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
    phases: list[GeneratedPhase] = Field(
        min_length=1
    )
    events: list[GeneratedEvent] = Field(
        default_factory=list
    )
    voting_moments: list[GeneratedVotingMoment] = Field(
        min_length=1
    )
    clues: list[GeneratedClue] = Field(
        min_length=1
    )


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
                "AI_PROVIDER_NOT_CONFIGURED: "
                "configureer AI_API_KEY voor echte gamegeneratie."
            )

        if not names:
            raise ValueError(
                "Er moet minimaal één speler zijn."
            )

        role_names = [
            str(role.get("name", "")).strip()
            for role in game.get("roles", [])
            if isinstance(role, dict)
            and str(role.get("name", "")).strip()
        ]

        if not role_names:
            raise ValueError(
                "De geselecteerde game heeft geen rollen."
            )

        # ----------------------------------------------------
        # Belangrijk:
        #
        # De AI MAG NIET de uiteindelijke rolverdeling bepalen.
        # Hij mag inhoud voor rollen schrijven, maar de backend
        # corrigeert de verdeling daarna.
        # ----------------------------------------------------

        player_payload = [
            {
                "player_id": str(index + 1),
                "name": name,
            }
            for index, name in enumerate(names)
        ]

        prompt = {
            "game_id": game["id"],
            "game_name": game["name"],
            "game_rules": game.get("rules", []),
            "available_roles": role_names,
            "players": player_payload,
            "theme": game.get("theme", {}),
            "objective": game.get("goal", ""),
            "difficulty": difficulty,
            "duration": duration,
            "clue_count_per_player": max(
                1,
                clue_count,
            ),
            "language": "Nederlands",
            "critical_role_rules": [
                "Er mag NOOIT meer dan één Boss zijn.",
                "De backend bepaalt uiteindelijk de rolverdeling.",
                "Gebruik uitsluitend rollen uit available_roles.",
                "Gebruik iedere player_id exact één keer.",
                "Gebruik de aangeleverde namen exact.",
                "Markeer alleen echte saboteurs met is_saboteur=true.",
                "Geef iedere speler unieke persoonlijke informatie.",
                "Geef iedere speler minimaal clue_count_per_player persoonlijke clues.",
                "Geef minimaal één Boss.",
                "Geef minimaal één saboteur.",
            ],
        }

        system_prompt = """
Je bent een professionele tabletop game designer.

Genereer uitsluitend één geldig JSON-object.
Gebruik GEEN markdown.
Gebruik GEEN code fences.
Gebruik GEEN uitleg buiten JSON.

ZEER BELANGRIJK:

1. player_id moet exact overeenkomen met de aangeleverde IDs.
2. name moet exact overeenkomen met de aangeleverde namen.
3. role moet een rol uit available_roles zijn.
4. Geef nooit meerdere spelers de rol Boss.
5. Geef iedere speler een betekenisvolle eigen rol.
6. Geef iedere speler eigen geheime informatie.
7. Geef iedere speler minimaal het gevraagde aantal clues.
8. Clues mogen niet allemaal exact hetzelfde zijn.
9. relationships is altijd een array van strings.
10. personal_objectives is altijd een array van objecten.
11. phases gebruiken alleen gehele getallen.
12. events gebruiken alleen gehele phase-nummers.
13. voting_moments gebruiken alleen gehele phase-nummers.
14. clues gebruiken alleen gehele release_phase-nummers.
15. clue_type moet één van de toegestane clue types zijn.
16. supports moet minimaal één item bevatten.
17. Alle spelergerichte tekst is Nederlands.

De uiteindelijke rolverdeling wordt door de backend gecontroleerd en
indien nodig gecorrigeerd. Probeer daarom zelf ook een logische,
gebalanceerde rolverdeling te maken.
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

                    if not isinstance(
                        content,
                        str,
                    ):
                        raise ValueError(
                            "AI returned invalid message content."
                        )

                    raw = json.loads(content)

                    raw = _normalize_generation(
                        raw,
                        names=names,
                        game=game,
                        clue_count=clue_count,
                    )

                    if hasattr(
                        GeneratedGame,
                        "model_validate",
                    ):
                        generated = (
                            GeneratedGame.model_validate(raw)
                        )
                    else:
                        generated = (
                            GeneratedGame.parse_obj(raw)
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
                    "AI validation failed attempt %s: %s",
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
                    "AI generation failed attempt %s",
                    attempt,
                )
                last_error = exc

            if attempt < 3:
                await asyncio.sleep(
                    0.75 * attempt
                )

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

    if isinstance(value, int):
        return max(1, value)

    if isinstance(value, float):
        return max(1, int(value))

    if isinstance(value, str):
        value_lower = value.lower().strip()

        if value_lower.isdigit():
            return max(
                1,
                int(value_lower),
            )

        for index, phase in enumerate(
            phases,
            start=1,
        ):
            if not isinstance(
                phase,
                dict,
            ):
                continue

            possible_values = {
                str(
                    phase.get(
                        "phase_id",
                        "",
                    )
                ).lower(),
                str(
                    phase.get(
                        "id",
                        "",
                    )
                ).lower(),
                str(
                    phase.get(
                        "name",
                        "",
                    )
                ).lower(),
            }

            if value_lower in possible_values:
                return index

    return 1


def _normalize_generation(
    raw: dict[str, Any],
    *,
    names: list[str],
    game: dict[str, Any],
    clue_count: int,
) -> dict[str, Any]:

    if not isinstance(
        raw,
        dict,
    ):
        raise ValueError(
            "AI output must be a JSON object."
        )

    # --------------------------------------------------------
    # PHASES
    # --------------------------------------------------------

    phases = raw.get(
        "phases",
        [],
    )

    if not isinstance(
        phases,
        list,
    ):
        phases = []

    normalized_phases = []

    for index, phase in enumerate(
        phases,
        start=1,
    ):
        if not isinstance(
            phase,
            dict,
        ):
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
                ).strip()
                or "Onderzoek de situatie.",
                "open_question": str(
                    phase.get(
                        "open_question",
                        phase.get(
                            "question",
                            "Wat is hier werkelijk gebeurd?",
                        ),
                    )
                ).strip()
                or "Wat is hier werkelijk gebeurd?",
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
                                "Onderzoek de situatie."
                            ],
                        ),
                    )
                ),
            }
        )

    if not normalized_phases:
        normalized_phases = [
            {
                "number": 1,
                "name": "Start",
                "purpose": (
                    "Verzamel de eerste informatie."
                ),
                "open_question": (
                    "Wat is er gebeurd?"
                ),
                "release_after_days": 0,
                "objectives": [
                    "Verzamel informatie."
                ],
            }
        ]

    raw["phases"] = normalized_phases

    # --------------------------------------------------------
    # PLAYERS
    # --------------------------------------------------------

    players = raw.get(
        "players",
        [],
    )

    if not isinstance(
        players,
        list,
    ):
        players = []

    # Maak een map op player_id zodat ontbrekende AI spelers
    # later automatisch kunnen worden toegevoegd.
    players_by_id: dict[str, dict[str, Any]] = {}

    for index, player in enumerate(
        players
    ):
        if not isinstance(
            player,
            dict,
        ):
            continue

        player_id = str(
            player.get(
                "player_id",
                index + 1,
            )
        )

        players_by_id[player_id] = player

    normalized_players = []

    for index, name in enumerate(
        names,
        start=1,
    ):
        player_id = str(index)

        player = players_by_id.get(
            player_id,
            {},
        )

        player_name = name

        relationships = _normalize_relationships(
            player.get(
                "relationships",
                [],
            )
        )

        clues = _normalize_player_clues(
            player.get(
                "clues",
                [],
            )
        )

        # Niet zomaar dezelfde globale clues kopiëren.
        # We maken ontbrekende persoonlijke clues.
        while len(clues) < max(
            2,
            clue_count,
        ):
            clues.append(
                _fallback_personal_clue(
                    player_id,
                    len(clues) + 1,
                )
            )

        objectives = _normalize_objectives(
            player.get(
                "personal_objectives",
                [],
            ),
            player_id,
            normalized_phases,
        )

        role = str(
            player.get(
                "role",
                "",
            )
        ).strip()

        role_description = str(
            player.get(
                "role_description",
                "",
            )
        ).strip()

        objective = str(
            player.get(
                "objective",
                "",
            )
        ).strip()

        secret_information = str(
            player.get(
                "secret_information",
                player.get(
                    "secret",
                    "",
                ),
            )
        ).strip()

        instructions = str(
            player.get(
                "instructions",
                "",
            )
        ).strip()

        if not objective:
            objective = (
                "Bereik je persoonlijke doel."
            )

        if not role_description:
            role_description = (
                "Speel je rol en gebruik je "
                "informatie verstandig."
            )

        if not secret_information:
            secret_information = (
                "Je beschikt over informatie die "
                "niet iedereen kent."
            )

        if not instructions:
            instructions = (
                "Werk samen, maar bepaal zelf "
                "welke informatie je deelt."
            )

        normalized_players.append(
            {
                "player_id": player_id,
                "name": player_name,
                "role": role,
                "role_description": role_description,
                "objective": objective,
                "personal_objectives": objectives,
                "secret_information": secret_information,
                "clues": clues,
                "relationships": relationships,
                "instructions": instructions,
                "is_saboteur": bool(
                    player.get(
                        "is_saboteur",
                        False,
                    )
                ),
            }
        )

    raw["players"] = normalized_players

    # --------------------------------------------------------
    # CRUCIALE FIX:
    # ROLLEN WORDEN HIER AFGEDWONGEN.
    # --------------------------------------------------------

    _repair_role_distribution(
        raw["players"],
        game,
    )

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    raw["events"] = _normalize_events(
        raw.get(
            "events",
            [],
        ),
        normalized_phases,
        len(names),
    )

    # --------------------------------------------------------
    # VOTING
    # --------------------------------------------------------

    raw["voting_moments"] = (
        _normalize_voting_moments(
            raw.get(
                "voting_moments",
                [],
            ),
            normalized_phases,
        )
    )

    # --------------------------------------------------------
    # GLOBAL CLUES
    # --------------------------------------------------------

    raw["clues"] = _normalize_global_clues(
        raw.get(
            "clues",
            [],
        ),
        names,
        normalized_phases,
        clue_count,
    )

    # --------------------------------------------------------
    # Globale clues moeten daadwerkelijk bij spelers horen.
    # --------------------------------------------------------

    _ensure_player_clues_are_unique(
        raw["players"],
        raw["clues"],
        clue_count,
    )

    return raw


# ============================================================
# ROLE REPAIR
# ============================================================


def _repair_role_distribution(
    players: list[dict[str, Any]],
    game: dict[str, Any],
) -> None:

    roles = [
        role
        for role in game.get(
            "roles",
            [],
        )
        if isinstance(
            role,
            dict,
        )
    ]

    role_names = [
        str(
            role.get(
                "name",
                "",
            )
        ).strip()
        for role in roles
    ]

    role_names = [
        role
        for role in role_names
        if role
    ]

    if not role_names:
        raise ValueError(
            "Geen geldige rollen gevonden."
        )

    # Case-insensitive zoeken.
    boss_role = _find_role(
        role_names,
        "boss",
    )

    saboteur_role = (
        _find_role(
            role_names,
            "double agent",
        )
        or _find_role(
            role_names,
            "saboteur",
        )
        or _find_role(
            role_names,
            "traitor",
        )
    )

    # --------------------------------------------------------
    # BOSS
    # --------------------------------------------------------

    # Altijd speler 1 als Boss.
    # Hierdoor kan de AI nooit 7 bosses teruggeven.
    if boss_role:
        players[0]["role"] = boss_role

        for player in players[1:]:
            if _same_role(
                player.get(
                    "role",
                    "",
                ),
                boss_role,
            ):
                player["role"] = ""

    # --------------------------------------------------------
    # SABOTEURS
    # --------------------------------------------------------

    if saboteur_role:
        requested_saboteurs = [
            player
            for player in players
            if player.get(
                "is_saboteur",
                False,
            )
        ]

        # Boss mag niet automatisch saboteur worden.
        requested_saboteurs = [
            player
            for player in requested_saboteurs
            if player["player_id"] != "1"
        ]

        # Als AI geen saboteur markeerde, kies speler 2.
        if not requested_saboteurs and len(players) >= 2:
            requested_saboteurs = [
                players[1]
            ]

        for player in players:
            player["is_saboteur"] = False

        for player in requested_saboteurs:
            player["is_saboteur"] = True
            player["role"] = saboteur_role

    # --------------------------------------------------------
    # OVERIGE ROLLEN
    # --------------------------------------------------------

    non_special_roles = [
        role
        for role in role_names
        if not (
            boss_role
            and _same_role(
                role,
                boss_role,
            )
        )
        and not (
            saboteur_role
            and _same_role(
                role,
                saboteur_role,
            )
        )
    ]

    if not non_special_roles:
        non_special_roles = [
            role
            for role in role_names
            if not (
                boss_role
                and _same_role(
                    role,
                    boss_role,
                )
            )
        ]

    role_index = 0

    for player in players:
        if (
            boss_role
            and player["player_id"] == "1"
        ):
            continue

        if player.get(
            "is_saboteur",
            False,
        ):
            continue

        current_role = str(
            player.get(
                "role",
                "",
            )
        ).strip()

        valid_current = (
            current_role in role_names
            and not (
                boss_role
                and _same_role(
                    current_role,
                    boss_role,
                )
            )
            and not (
                saboteur_role
                and _same_role(
                    current_role,
                    saboteur_role,
                )
            )
        )

        if not valid_current:
            if non_special_roles:
                player["role"] = (
                    non_special_roles[
                        role_index
                        % len(non_special_roles)
                    ]
                )
                role_index += 1
            else:
                player["role"] = role_names[
                    min(
                        role_index,
                        len(role_names) - 1,
                    )
                ]
                role_index += 1


def _find_role(
    roles: list[str],
    wanted: str,
) -> str | None:

    wanted = wanted.lower().strip()

    for role in roles:
        if role.lower().strip() == wanted:
            return role

    return None


def _same_role(
    first: Any,
    second: Any,
) -> bool:

    return (
        str(first).strip().lower()
        == str(second).strip().lower()
    )


# ============================================================
# PLAYER CLUES
# ============================================================


def _normalize_player_clues(
    value: Any,
) -> list[str]:

    if isinstance(
        value,
        str,
    ):
        return [
            value.strip()
        ] if value.strip() else []

    if not isinstance(
        value,
        list,
    ):
        return []

    result = []

    for item in value:
        if isinstance(
            item,
            dict,
        ):
            text = item.get(
                "text",
                item.get(
                    "description",
                    "",
                ),
            )
        else:
            text = item

        text = str(
            text
        ).strip()

        if text and text not in result:
            result.append(text)

    return result


def _fallback_personal_clue(
    player_id: str,
    number: int,
) -> str:

    return (
        f"Persoonlijke observatie van speler "
        f"{player_id}: je hebt informatie die "
        f"later relevant kan zijn voor het onderzoek "
        f"(clue {number})."
    )


def _ensure_player_clues_are_unique(
    players: list[dict[str, Any]],
    global_clues: list[dict[str, Any]],
    clue_count: int,
) -> None:

    minimum = max(
        2,
        clue_count,
    )

    for player in players:
        clues = _normalize_player_clues(
            player.get(
                "clues",
                [],
            )
        )

        while len(clues) < minimum:
            clues.append(
                _fallback_personal_clue(
                    player["player_id"],
                    len(clues) + 1,
                )
            )

        player["clues"] = clues


# ============================================================
# OBJECTIVES
# ============================================================


def _normalize_objectives(
    objectives: Any,
    player_id: str,
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    if isinstance(
        objectives,
        dict,
    ):
        objectives = [
            objectives
        ]

    if not isinstance(
        objectives,
        list,
    ):
        objectives = []

    normalized = []

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

    for index, objective in enumerate(
        objectives,
        start=1,
    ):
        if not isinstance(
            objective,
            dict,
        ):
            continue

        metric = str(
            objective.get(
                "metric",
                "manual_review",
            )
        ).lower().strip()

        metric = metric_map.get(
            metric,
            metric,
        )

        if metric not in allowed_metrics:
            metric = "manual_review"

        text = str(
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
        ).strip()

        if not text:
            text = (
                "Bereik je persoonlijke doel."
            )

        normalized.append(
            {
                "id": str(
                    objective.get(
                        "id",
                        f"{player_id}-objective-{index}",
                    )
                ),
                "text": text,
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
                "activate_phase": _phase_number(
                    objective.get(
                        "activate_phase",
                        1,
                    ),
                    phases,
                ),
            }
        )

    if not normalized:
        normalized.append(
            {
                "id": (
                    f"{player_id}-objective-1"
                ),
                "text": (
                    "Bereik je persoonlijke doel."
                ),
                "owner_player_id": player_id,
                "measurable": False,
                "metric": "manual_review",
                "target_player_id": None,
                "target_value": None,
                "activate_phase": 1,
            }
        )

    return normalized


# ============================================================
# RELATIONSHIPS
# ============================================================


def _normalize_relationships(
    value: Any,
) -> list[str]:

    if isinstance(
        value,
        dict,
    ):
        return [
            f"{key}: {item}"
            for key, item in value.items()
        ]

    if isinstance(
        value,
        str,
    ):
        return [
            value
        ] if value.strip() else []

    if not isinstance(
        value,
        list,
    ):
        return []

    return [
        str(item).strip()
        for item in value
        if str(item).strip()
    ]


# ============================================================
# EVENTS
# ============================================================


def _normalize_events(
    events: Any,
    phases: list[dict[str, Any]],
    player_count: int,
) -> list[dict[str, Any]]:

    if not isinstance(
        events,
        list,
    ):
        events = []

    result = []

    for index, event in enumerate(
        events,
        start=1,
    ):
        if not isinstance(
            event,
            dict,
        ):
            continue

        player_ids = event.get(
            "player_ids",
            [],
        )

        if isinstance(
            player_ids,
            str,
        ):
            player_ids = [
                player_ids
            ]

        if not isinstance(
            player_ids,
            list,
        ):
            player_ids = []

        player_ids = [
            str(player_id)
            for player_id in player_ids
            if str(player_id).isdigit()
            and 1
            <= int(player_id)
            <= player_count
        ]

        if not player_ids:
            player_ids = [
                str(
                    ((index - 1) % player_count)
                    + 1
                )
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
                ).strip()
                or f"Event {index}",
                "description": str(
                    event.get(
                        "description",
                        event.get(
                            "details",
                            "Er gebeurt iets onverwachts.",
                        ),
                    )
                ).strip(),
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
                "player_ids": player_ids,
            }
        )

    return result


# ============================================================
# VOTING
# ============================================================


def _normalize_voting_moments(
    voting_moments: Any,
    phases: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    if not isinstance(
        voting_moments,
        list,
    ):
        voting_moments = []

    result = []

    for index, voting in enumerate(
        voting_moments,
        start=1,
    ):
        if not isinstance(
            voting,
            dict,
        ):
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
                ).strip()
                or "Wie verdenken jullie?",
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

    if not result:
        result.append(
            {
                "id": "vote-1",
                "phase": 1,
                "question": (
                    "Wie verdenken jullie "
                    "op dit moment?"
                ),
                "release_after_days": 0,
                "duration_hours": 24,
            }
        )

    return result


# ============================================================
# GLOBAL CLUES
# ============================================================


def _normalize_global_clues(
    clues: Any,
    names: list[str],
    phases: list[dict[str, Any]],
    clue_count: int,
) -> list[dict[str, Any]]:

    if not isinstance(
        clues,
        list,
    ):
        clues = []

    result = []

    allowed_types = {
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

    clue_type_map = {
        "information": "direct",
        "info": "direct",
        "fact": "direct",
        "evidence": "confirming",
        "secret": "personal",
        "hint": "indirect",
        "important": "crucial",
    }

    for index, clue in enumerate(
        clues,
        start=1,
    ):
        if not isinstance(
            clue,
            dict,
        ):
            continue

        text = str(
            clue.get(
                "text",
                clue.get(
                    "description",
                    "",
                ),
            )
        ).strip()

        if not text:
            continue

        clue_type = str(
            clue.get(
                "clue_type",
                "direct",
            )
        ).lower().strip()

        clue_type = clue_type_map.get(
            clue_type,
            clue_type,
        )

        if clue_type not in allowed_types:
            clue_type = "direct"

        supports = clue.get(
            "supports",
            [],
        )

        if isinstance(
            supports,
            str,
        ):
            supports = [
                supports
            ]

        if not isinstance(
            supports,
            list,
        ):
            supports = []

        supports = [
            str(item).strip()
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

        if isinstance(
            dependencies,
            str,
        ):
            dependencies = [
                dependencies
            ]

        if not isinstance(
            dependencies,
            list,
        ):
            dependencies = []

        owner = str(
            clue.get(
                "owner_player_id",
                "1",
            )
        )

        if (
            not owner.isdigit()
            or not 1
            <= int(owner)
            <= len(names)
        ):
            owner = "1"

        result.append(
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
                "owner_player_id": owner,
                "release_phase": _phase_number(
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
                ),
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

    # --------------------------------------------------------
    # Zorg dat er genoeg globale clues zijn.
    # --------------------------------------------------------

    minimum = (
        len(names)
        * max(
            1,
            clue_count,
        )
    )

    existing_texts = {
        clue["text"]
        for clue in result
    }

    next_id = len(result) + 1

    while len(result) < minimum:
        owner = (
            (len(result) % len(names))
            + 1
        )

        text = (
            f"Een extra observatie rond speler "
            f"{owner} kan later belangrijk blijken."
        )

        # absoluut geen duplicate IDs/text.
        while text in existing_texts:
            text = (
                f"Een extra observatie rond speler "
                f"{owner} kan later belangrijk blijken "
                f"({next_id})."
            )

        result.append(
            {
                "id": f"clue-{next_id}",
                "text": text,
                "clue_type": "indirect",
                "owner_player_id": str(owner),
                "release_phase": 1,
                "visibility": "private",
                "supports": [
                    "investigation"
                ],
                "dependencies": [],
                "red_herring": False,
            }
        )

        existing_texts.add(text)
        next_id += 1

    return result


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

        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def _string_list(
    value: Any,
) -> list[str]:

    if isinstance(
        value,
        str,
    ):
        value = [
            value
        ]

    if not isinstance(
        value,
        list,
    ):
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


def _normalize_delivery(
    value: Any,
) -> str:

    allowed = {
        "website",
        "email",
        "physical_clue",
        "qr_code",
        "whatsapp",
        "printed_document",
    }

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
        "document": "printed_document",
        "print": "printed_document",
    }

    value = mapping.get(
        value,
        value,
    )

    return (
        value
        if value in allowed
        else "website"
    )


def _normalize_visibility(
    value: Any,
) -> str:

    allowed = {
        "public",
        "private",
        "shareable",
    }

    value = str(
        value
    ).lower().strip()

    mapping = {
        "shared": "shareable",
        "everyone": "public",
        "all": "public",
        "secret": "private",
    }

    value = mapping.get(
        value,
        value,
    )

    return (
        value
        if value in allowed
        else "public"
    )


# ============================================================
# VALIDATION
# ============================================================


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

    expected_ids = {
        str(index + 1)
        for index in range(len(names))
    }

    actual_ids = {
        player.player_id
        for player in generated.players
    }

    if actual_ids != expected_ids:
        raise ValueError(
            "player_id values must be unique "
            "and sequential"
        )

    role_names = {
        str(role.get("name", "")).strip()
        for role in game.get(
            "roles",
            [],
        )
        if isinstance(
            role,
            dict,
        )
    }

    # --------------------------------------------------------
    # PLAYER VALIDATION
    # --------------------------------------------------------

    boss_players = []

    for index, player in enumerate(
        generated.players
    ):
        expected_id = str(
            index + 1
        )

        if player.player_id != expected_id:
            raise ValueError(
                f"player {index + 1} "
                f"has invalid player_id"
            )

        if player.name != names[index]:
            raise ValueError(
                f"player {index + 1} "
                f"has invalid name"
            )

        if player.role not in role_names:
            raise ValueError(
                f"player {index + 1} "
                f"has invalid role: "
                f"{player.role}"
            )

        if (
            player.role.lower().strip()
            == "boss"
        ):
            boss_players.append(
                player
            )

        if len(player.clues) < max(
            2,
            clue_count,
        ):
            raise ValueError(
                f"player {index + 1} "
                f"has insufficient clues"
            )

        if not player.objective.strip():
            raise ValueError(
                f"player {index + 1} "
                f"has no objective"
            )

        if not player.instructions.strip():
            raise ValueError(
                f"player {index + 1} "
                f"has no instructions"
            )

    # --------------------------------------------------------
    # EXACTLY ONE BOSS
    # --------------------------------------------------------

    if boss_players and len(
        boss_players
    ) != 1:
        raise ValueError(
            f"expected exactly one Boss, "
            f"received {len(boss_players)}"
        )

    # --------------------------------------------------------
    # SABOTEURS
    # --------------------------------------------------------

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
            "saboteur_count does not match "
            "player assignments"
        )

    # --------------------------------------------------------
    # PHASES
    # --------------------------------------------------------

    minimum_phases = (
        5
        if requested_duration == "1_maand"
        else 3
        if requested_duration in {
            "2_weken",
            "3_weken",
        }
        else 1
    )

    minimum_votes = (
        3
        if requested_duration == "1_maand"
        else 2
        if requested_duration in {
            "2_weken",
            "3_weken",
        }
        else 1
    )

    if len(generated.phases) < minimum_phases:
        raise ValueError(
            f"duration requires at least "
            f"{minimum_phases} phases"
        )

    if len(
        generated.voting_moments
    ) < minimum_votes:
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

    # --------------------------------------------------------
    # VOTING
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

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
            if player_id not in actual_ids:
                raise ValueError(
                    f"event {event.id} "
                    f"references unknown player "
                    f"{player_id}"
                )

    # --------------------------------------------------------
    # GLOBAL CLUES
    # --------------------------------------------------------

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
        len(names)
        * max(
            1,
            clue_count,
        )
    )

    if len(
        generated.clues
    ) < minimum_global_clues:
        raise ValueError(
            f"expected at least "
            f"{minimum_global_clues} global clues, "
            f"received "
            f"{len(generated.clues)}"
        )

    for clue in generated.clues:

        if clue.owner_player_id not in actual_ids:
            raise ValueError(
                f"clue {clue.id} references "
                f"unknown owner "
                f"{clue.owner_player_id}"
            )

        if clue.release_phase not in phase_numbers:
            raise ValueError(
                f"clue {clue.id} references "
                f"unknown phase "
                f"{clue.release_phase}"
            )

        for dependency in clue.dependencies:
            if dependency not in clue_ids:
                raise ValueError(
                    f"clue {clue.id} references "
                    f"unknown dependency "
                    f"{dependency}"
                )


ai_service = AIService()