from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.ai import GENERIC_FALLBACK, generate_reflection
from app.auth import current_user
from app.config import settings
from app.database import Base, engine, get_db
from app.models import CheckIn, User
from app.ratelimit import client_ip, ip_limit, limiter
from app.safety import get_crisis_message, get_crisis_resources, may_need_immediate_support
from app.schemas import (
    CheckInCreate, CheckInResponse, CheckInUpdate, CrisisResource, ErrorResponse, LoginRequest, ReframeRequest,
    ReframeResponse, RegisterRequest, TokenResponse, UserResponse, VentRequest, VentResponse,
)
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password

AUTH_401 = {401: {"model": ErrorResponse, "description": "Missing, invalid or expired token."}}
RATE_429 = {429: {"model": ErrorResponse, "description": "Rate limited. See the Retry-After header."}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suitable for the initial MVP; use Alembic migrations for production schema changes.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description=(
        "AirSpace MVP API: vent, reflect, and track emotional check-ins.\n\n"
        "Errors: business errors are `{\"detail\": \"message\"}`; validation errors (422) return "
        "`detail` as a list of `{loc, msg, type}` objects."
    ),
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
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
        acknowledgement=(
            "You can put it into words here without needing to make it sound neat. "
            "You do not have to solve it all in this moment."
        ),
        reflection_prompts=[
            "What feels heaviest about this right now?",
            "What do you wish someone understood?",
            "What would help you feel a little more supported in the next few minutes?",
        ],
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
            ai_enabled=bool(settings.openai_api_key),
            ai_status="skipped_for_safety",
        )

    if not settings.openai_api_key:
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
