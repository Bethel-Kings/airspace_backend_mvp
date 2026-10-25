from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class VentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    # Consent is explicit; raw text is not stored unless the server is configured to persist it.
    consent_to_store: bool = False

class ReframeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    prompt_style: str = Field(default="gentle", pattern="^(gentle|practical|reflective)$")

class VentResponse(BaseModel):
    acknowledgement: str
    reflection_prompts: list[str]
    safety_notice: str | None = None
    stored: bool = False

class CheckInCreate(BaseModel):
    before_score: int = Field(ge=1, le=10)
    after_score: int | None = Field(default=None, ge=1, le=10)
    emotion: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)

class CheckInResponse(BaseModel):
    id: int
    before_score: int
    after_score: int | None
    emotion: str | None
    note: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
