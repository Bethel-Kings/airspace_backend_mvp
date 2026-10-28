from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

AiStatus = Literal["skipped_for_safety", "unavailable", "consent_required", "success", "fallback"]


class ErrorResponse(BaseModel):
    detail: str


class CrisisResource(BaseModel):
    name: str
    phone: str
    alt_phone: str | None = None
    hours: str
    description: str
    url: str = ""


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v


class VentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


class ReframeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    prompt_style: str = Field(default="gentle", pattern="^(gentle|practical|reflective)$")
    # Frontend must disclose external AI processing and obtain opt-in first.
    consent_to_ai_processing: bool = False


ChatRole = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    # "system" is deliberately not accepted: clients must not be able to inject instructions.
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """Stateless chat: the client sends the running conversation; the server stores nothing."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    prompt_style: str = Field(default="gentle", pattern="^(gentle|practical|reflective)$")
    # Frontend must disclose external AI processing and obtain opt-in first.
    consent_to_ai_processing: bool = False

    @model_validator(mode="after")
    def _valid_conversation(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        if sum(len(m.content) for m in self.messages) > 12000:
            raise ValueError("Conversation is too long. Send fewer or shorter messages.")
        return self


class ChatResponse(BaseModel):
    reply: str | None = None
    safety_notice: str | None = None
    crisis_resources: list[CrisisResource] | None = None
    needs_human_support: bool = False
    ai_enabled: bool
    ai_status: AiStatus
    consent_required: bool = False


class VoiceVentResponse(BaseModel):
    transcript: str | None = None
    # Present only when `reflect=true` and nothing was flagged.
    reply: str | None = None
    acknowledgement: str | None = None
    reflection_prompts: list[str] | None = None
    safety_notice: str | None = None
    crisis_resources: list[CrisisResource] | None = None
    needs_human_support: bool = False
    ai_enabled: bool
    ai_status: AiStatus
    consent_required: bool = False
    stored: bool = False


class VentResponse(BaseModel):
    acknowledgement: str
    reflection_prompts: list[str]
    safety_notice: str | None = None
    crisis_resources: list[CrisisResource] | None = None
    stored: bool = False


class ReframeResponse(BaseModel):
    reflection: str | None = None
    safety_notice: str | None = None
    crisis_resources: list[CrisisResource] | None = None
    needs_human_support: bool = False
    ai_enabled: bool
    ai_status: AiStatus
    consent_required: bool = False


class CheckInCreate(BaseModel):
    before_score: int = Field(ge=1, le=10)
    after_score: int | None = Field(default=None, ge=1, le=10)
    emotion: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class CheckInUpdate(BaseModel):
    """Partial update. Send only the fields to change; an explicit null clears that field."""

    model_config = ConfigDict(extra="forbid")
    after_score: int | None = Field(default=None, ge=1, le=10)
    emotion: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _at_least_one(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one of: after_score, emotion, note.")
        return self


class CheckInResponse(BaseModel):
    id: int
    before_score: int
    after_score: int | None
    emotion: str | None
    note: str | None
    created_at: datetime
    # Set on create/update responses when the emotion or note text trips the safety check.
    safety_notice: str | None = None
    crisis_resources: list[CrisisResource] | None = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        # SQLite drops tzinfo; values are always UTC.
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
