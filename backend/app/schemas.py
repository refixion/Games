from pydantic import BaseModel, EmailStr

class JoinIn(BaseModel):
    name: str
    email: EmailStr

class GenericResponse(BaseModel):
    success: bool
    message: str

