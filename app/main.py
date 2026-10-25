from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.ai import GENERIC_FALLBACK, generate_reflection
from app.auth import current_user
from app.config import settings
from app.database import Base, engine, get_db
from app.models import CheckIn, User
from app.safety import CRISIS_MESSAGE, may_need_immediate_support
from app.schemas import (
    CheckInCreate, CheckInResponse, LoginRequest, ReframeRequest, ReframeResponse,
    RegisterRequest, TokenResponse, VentRequest, VentResponse,
)
from app.security import create_access_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Suitable for the initial MVP; use Alembic migrations for production schema changes.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="AirSpace MVP API: vent, reflect, and track emotional check-ins.",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "airspace-api"}


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
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


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = str(payload.email).lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.post("/api/v1/vent", response_model=VentResponse)
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
        safety_notice=CRISIS_MESSAGE if crisis else None,
        stored=False,
    )


@app.post("/api/v1/reframe", response_model=ReframeResponse)
async def reframe(payload: ReframeRequest, user: User = Depends(current_user)):
    # Do not route a flagged message through ordinary AI reframing.
    if may_need_immediate_support(payload.text):
        return ReframeResponse(
            reflection=None,
            safety_notice=CRISIS_MESSAGE,
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

    result = await generate_reflection(payload.text, payload.prompt_style)
    return ReframeResponse(reflection=result.text, ai_enabled=True, ai_status=result.status)


@app.post("/api/v1/checkins", response_model=CheckInResponse, status_code=201)
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
    return item


@app.get("/api/v1/checkins", response_model=list[CheckInResponse])
def list_checkins(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = (
        select(CheckIn)
        .where(CheckIn.user_id == user.id)
        .order_by(CheckIn.created_at.desc())
        .limit(100)
    )
    return list(db.scalars(query))


@app.delete("/api/v1/checkins/{checkin_id}", status_code=204)
def delete_checkin(checkin_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.scalar(select(CheckIn).where(CheckIn.id == checkin_id, CheckIn.user_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="Check-in not found.")
    db.delete(item)
    db.commit()
    return None


@app.delete("/api/v1/account", status_code=204)
def delete_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(user)
    db.commit()
    return None
