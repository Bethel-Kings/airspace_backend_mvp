from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.ai import ALLOWED_AUDIO_EXTENSIONS, GENERIC_FALLBACK, generate_chat_reply, generate_reflection, transcribe_audio
from app.auth import current_user
from app.config import settings
from app.database import Base, engine, get_db
from app.models import CheckIn, User
from app.ratelimit import client_ip, ip_limit, limiter
from app.safety import get_crisis_message, get_crisis_resources, may_need_immediate_support
from app.schemas import (
    ChatRequest, ChatResponse, CheckInCreate, CheckInResponse, CheckInUpdate, CrisisResource, ErrorResponse,
    LoginRequest, ReframeRequest, ReframeResponse, RegisterRequest, TokenResponse, UserResponse, VentRequest,
    VentResponse, VoiceVentResponse,
)
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password

AUTH_401 = {401: {"model": ErrorResponse, "description": "Missing, invalid or expired token."}}
RATE_429 = {429: {"model": ErrorResponse, "description": "Rate limited. See the Retry-After header."}}

VENT_ACKNOWLEDGEMENT = (
    "You can put it into words here without needing to make it sound neat. "
    "You do not have to solve it all in this moment."
)
VENT_PROMPTS = [
    "What feels heaviest about this right now?",
    "What do you wish someone understood?",
    "What would help you feel a little more supported in the next few minutes?",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suitable for the initial MVP; use Alembic migrations for production schema changes.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description=(
        "AirSpace MVP API: vent (text or voice), chat, reflect, and track emotional check-ins.\n\n"
        "Errors: business errors are `{\"detail\": \"message\"}`; validation errors (422) return "
        "`detail` as a list of `{loc, msg, type}` objects."
    ),
    lifespan=lifespan,
)

raw_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
origins = list({o for origin in raw_origins for o in (origin, origin.rstrip("/")) if o})
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def with_safety_notice(item: CheckIn) -> CheckInResponse:
    response = CheckInResponse.model_validate(item)
    if may_need_immediate_support(item.note) or may_need_immediate_support(item.emotion):
        response.safety_notice = get_crisis_message()
        response.crisis_resources = get_crisis_resources()
    return response


@app.get("/health", tags=["system"], summary="Liveness check")
def health():
    return {"status": "ok", "service": "airspace-api"}


@app.get(
    "/api/v1/crisis-resources",
    response_model=list[CrisisResource],
    tags=["safety"],
    summary="List crisis intervention and mental health support resources",
)
def list_crisis_resources():
    return get_crisis_resources()


@app.post(
    "/api/v1/auth/register", response_model=TokenResponse, status_code=201, tags=["auth"],
    summary="Create account and sign in",
    responses={409: {"model": ErrorResponse, "description": "Email already registered."}, **RATE_429},
    dependencies=[Depends(ip_limit("register", 10, 3600))],
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.post(
    "/api/v1/auth/login", response_model=TokenResponse, tags=["auth"], summary="Sign in",
    responses={401: {"model": ErrorResponse, "description": "Invalid email or password."}, **RATE_429},
    dependencies=[Depends(ip_limit("login", 20, 300))],
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    limiter.check(f"login:email:{email}", 10, 300)  # slows distributed guessing against one account
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(payload.password, DUMMY_HASH)  # equalize timing with the real-user path
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.get("/api/v1/me", response_model=UserResponse, tags=["account"], summary="Current user (token check)",
         responses=AUTH_401)
def me(user: User = Depends(current_user)):
    return user


@app.post("/api/v1/vent", response_model=VentResponse, tags=["vent"],
          summary="Submit vent text (never stored)", responses=AUTH_401)
def vent(payload: VentRequest, user: User = Depends(current_user)):
    # Submitted vent text is checked transiently; this endpoint neither stores nor forwards it to AI.
    crisis = may_need_immediate_support(payload.text)
    return VentResponse(
        acknowledgement=VENT_ACKNOWLEDGEMENT,
        reflection_prompts=list(VENT_PROMPTS),
        safety_notice=get_crisis_message() if crisis else None,
        crisis_resources=get_crisis_resources() if crisis else None,
        stored=False,
    )


@app.post("/api/v1/reframe", response_model=ReframeResponse, tags=["vent"],
          summary="Reflection (generic fallback or consented AI)", responses={**AUTH_401, **RATE_429})
async def reframe(payload: ReframeRequest, request: Request, user: User = Depends(current_user)):
    # Do not route a flagged message through ordinary AI reframing.
    if may_need_immediate_support(payload.text):
        return ReframeResponse(
            reflection=None,
            safety_notice=get_crisis_message(),
            crisis_resources=get_crisis_resources(),
            needs_human_support=True,
            ai_enabled=settings.ai_enabled,
            ai_status="skipped_for_safety",
        )

    if not settings.ai_enabled:
        # This generic fallback does not use or transmit the submitted text.
        return ReframeResponse(
            reflection=GENERIC_FALLBACK,
            ai_enabled=False,
            ai_status="unavailable",
        )

    # External AI processing requires explicit opt-in from the user.
    if not payload.consent_to_ai_processing:
        return ReframeResponse(
            reflection=None,
            ai_enabled=True,
            ai_status="consent_required",
            consent_required=True,
        )

    # Only paid AI calls are limited, so a user in distress is never throttled out of safety messaging.
    limiter.check(f"reframe:user:{user.id}", 30, 3600)
    limiter.check(f"reframe:ip:{client_ip(request)}", 100, 3600)
    result = await generate_reflection(payload.text, payload.prompt_style)
    return ReframeResponse(reflection=result.text, ai_enabled=True, ai_status=result.status)


@app.post(
    "/api/v1/vent/voice", response_model=VoiceVentResponse, tags=["vent"],
    summary="Voice vent: transcribe audio (consented AI), optionally reflect. Audio is never stored.",
    responses={
        **AUTH_401, **RATE_429,
        413: {"model": ErrorResponse, "description": "Audio file too large."},
        415: {"model": ErrorResponse, "description": "Unsupported audio format."},
    },
)
async def vent_voice(
    request: Request,
    audio: UploadFile = File(..., description="Recorded audio (webm, ogg, mp4/m4a, mp3, wav, flac)."),
    consent_to_ai_processing: bool = Form(False),
    reflect: bool = Form(False, description="Also return an AI reply to the transcript."),
    prompt_style: str = Form("gentle", pattern="^(gentle|practical|reflective)$"),
    language: str | None = Form(None, pattern="^[a-z]{2}$", description="Optional ISO-639-1 hint, e.g. en, ig, yo, ha."),
    user: User = Depends(current_user),
):
    if not settings.transcription_enabled:
        # No server-side transcription. The client can fall back to on-device speech recognition + POST /vent.
        return VoiceVentResponse(ai_enabled=False, ai_status="unavailable")
    if not consent_to_ai_processing:
        return VoiceVentResponse(ai_enabled=True, ai_status="consent_required", consent_required=True)

    ext = (audio.filename or "").rsplit(".", 1)[-1].lower() if "." in (audio.filename or "") else ""
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_audio_bytes + 64 * 1024:
        raise HTTPException(status_code=413, detail="Audio file is too large.")
    data = await audio.read(settings.max_audio_bytes + 1)
    if len(data) > settings.max_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio file is too large.")
    if not data:
        raise HTTPException(status_code=422, detail="Audio file is empty.")

    # Paid calls only; crisis handling below is never throttled because it happens after transcription.
    limiter.check(f"voice:user:{user.id}", 20, 3600)
    limiter.check(f"voice:ip:{client_ip(request)}", 60, 3600)

    transcription = await transcribe_audio(data, ext, audio.content_type, language)
    del data  # audio is never persisted
    if transcription.text is None or not transcription.text:
        # Provider failure or no speech detected: the client should offer typing instead.
        return VoiceVentResponse(ai_enabled=True, ai_status="fallback")
    transcript = transcription.text

    if may_need_immediate_support(transcript):
        return VoiceVentResponse(
            transcript=transcript,
            safety_notice=get_crisis_message(),
            crisis_resources=get_crisis_resources(),
            needs_human_support=True,
            ai_enabled=True,
            ai_status="skipped_for_safety",
        )
    if not reflect or not settings.ai_enabled:
        # Also taken when no text-AI key is configured: transcript + static prompts, no generated reply.
        return VoiceVentResponse(
            transcript=transcript,
            acknowledgement=VENT_ACKNOWLEDGEMENT,
            reflection_prompts=list(VENT_PROMPTS),
            ai_enabled=True,
            ai_status="success",
        )
    result = await generate_reflection(transcript, prompt_style, voice=True)
    return VoiceVentResponse(transcript=transcript, reply=result.text, ai_enabled=True, ai_status=result.status)


@app.post("/api/v1/chat", response_model=ChatResponse, tags=["chat"],
          summary="Stateless AI chat turn (consented). Nothing is stored.", responses={**AUTH_401, **RATE_429})
async def chat(payload: ChatRequest, request: Request, user: User = Depends(current_user)):
    # Every user turn in the window is screened, so an earlier flagged message cannot be skipped by resending.
    if any(m.role == "user" and may_need_immediate_support(m.content) for m in payload.messages):
        return ChatResponse(
            safety_notice=get_crisis_message(),
            crisis_resources=get_crisis_resources(),
            needs_human_support=True,
            ai_enabled=settings.ai_enabled,
            ai_status="skipped_for_safety",
        )
    if not settings.ai_enabled:
        return ChatResponse(reply=GENERIC_FALLBACK, ai_enabled=False, ai_status="unavailable")
    if not payload.consent_to_ai_processing:
        return ChatResponse(ai_enabled=True, ai_status="consent_required", consent_required=True)

    limiter.check(f"chat:user:{user.id}", 60, 3600)
    limiter.check(f"chat:ip:{client_ip(request)}", 200, 3600)
    result = await generate_chat_reply([m.model_dump() for m in payload.messages], payload.prompt_style)
    return ChatResponse(reply=result.text, ai_enabled=True, ai_status=result.status)


@app.post("/api/v1/checkins", response_model=CheckInResponse, status_code=201, tags=["checkins"],
          summary="Save a check-in", responses=AUTH_401)
def create_checkin(payload: CheckInCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = CheckIn(
        user_id=user.id,
        before_score=payload.before_score,
        after_score=payload.after_score,
        emotion=payload.emotion,
        note=payload.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return with_safety_notice(item)


@app.get("/api/v1/checkins", response_model=list[CheckInResponse], tags=["checkins"],
         summary="List check-ins (newest first, max 100)", responses=AUTH_401)
def list_checkins(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = (
        select(CheckIn)
        .where(CheckIn.user_id == user.id)
        .order_by(CheckIn.created_at.desc(), CheckIn.id.desc())
        .limit(100)
    )
    return list(db.scalars(query))


@app.patch("/api/v1/checkins/{checkin_id}", response_model=CheckInResponse, tags=["checkins"],
           summary="Update after_score / emotion / note",
           responses={**AUTH_401, 404: {"model": ErrorResponse, "description": "Check-in not found."}})
def update_checkin(checkin_id: int, payload: CheckInUpdate, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    item = db.scalar(select(CheckIn).where(CheckIn.id == checkin_id, CheckIn.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="Check-in not found.")
    for field in payload.model_fields_set:
        setattr(item, field, getattr(payload, field))
    db.commit()
    db.refresh(item)
    return with_safety_notice(item)


@app.delete("/api/v1/checkins/{checkin_id}", status_code=204, tags=["checkins"], summary="Delete a check-in",
            responses={**AUTH_401, 404: {"model": ErrorResponse, "description": "Check-in not found."}})
def delete_checkin(checkin_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(CheckIn).where(CheckIn.id == checkin_id, CheckIn.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="Check-in not found.")
    db.delete(item)
    db.commit()
    return None


@app.delete("/api/v1/account", status_code=204, tags=["account"],
            summary="Delete account and all check-ins", responses=AUTH_401)
def delete_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(user)
    db.commit()
    return None
