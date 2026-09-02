from pydantic import BaseModel, EmailStr

class JoinIn(BaseModel):
    name: str
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
    game_preset: str

