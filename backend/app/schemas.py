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


class PollIn(BaseModel):
    question: str = Field(min_length=3, max_length=240)
    options: list[str] = Field(min_length=2, max_length=8)

