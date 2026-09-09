from typing import Literal

from pydantic import BaseModel, EmailStr, Field

class JoinIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr

class GenericResponse(BaseModel):
    success: bool
    message: str


class GameSelectIn(BaseModel):
    game_preset: str


class StatusIn(BaseModel):
    status: str


class ToggleIn(BaseModel):
    active: bool


class VoteIn(BaseModel):
    option_id: int


class SuspicionVoteIn(BaseModel):
    candidate_player_id: int = Field(ge=1)


class DurationIn(BaseModel):
    duration: Literal['avond', '1_week', '2_weken', '3_weken', '1_maand']


class PollIn(BaseModel):
    question: str = Field(min_length=3, max_length=240)
    options: list[str] = Field(min_length=2, max_length=8)


class GenerateIn(BaseModel):
    player_count: int = Field(default=7, ge=2, le=30)
    difficulty: Literal['easy', 'medium', 'hard'] = 'medium'
    duration: Literal['avond', '1_week', '2_weken', '3_weken', '1_maand'] = 'avond'
    clue_count: int = Field(default=3, ge=2, le=8)

