from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


class ReframeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    prompt_style: str = Field(default="gentle", pattern="^(gentle|practical|reflective)$")
    # Frontend must disclose external AI processing and obtain opt-in first.
    consent_to_ai_processing: bool = False


class VentResponse(BaseModel):
    acknowledgement: str
    reflection_prompts: list[str]
    safety_notice: str | None = None
    stored: bool = False


class ReframeResponse(BaseModel):
    reflection: str | None = None
    safety_notice: str | None = None
    needs_human_support: bool = False
    ai_enabled: bool
    ai_status: str
    consent_required: bool = False


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
