from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.ai import generate_reflection
from app.auth import current_user
from app.config import settings
from app.database import Base, engine, get_db
from app.models import CheckIn, User
from app.safety import CRISIS_MESSAGE, may_need_immediate_support
from app.schemas import (
    CheckInCreate, CheckInResponse, LoginRequest, ReframeRequest, RegisterRequest,
    TokenResponse, VentRequest, VentResponse,
)
from app.security import create_access_token, hash_password, verify_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AirSpace MVP backend: vent, reflect, and track emotional check-ins.",
    lifespan=lifespan,
)

origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "airspace-api"}

@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
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
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)))

@app.post("/api/v1/vent", response_model=VentResponse)
async def vent(payload: VentRequest, user: User = Depends(current_user)):
    # MVP intentionally does not persist the vent text. consent_to_store is reserved for a
    # future, explicit storage feature and does not override server-side privacy configuration.
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

@app.post("/api/v1/reframe")
async def reframe(payload: ReframeRequest, user: User = Depends(current_user)):
    crisis = may_need_immediate_support(payload.text)
    if crisis:
        # Do not attempt to reframe crisis language as ordinary stress.
        return {"reflection": None, "safety_notice": CRISIS_MESSAGE, "needs_human_support": True}
    reflection = await generate_reflection(payload.text, payload.prompt_style)
    return {
        "reflection": reflection,
        "safety_notice": None,
        "needs_human_support": False,
        "ai_enabled": bool(settings.openai_api_key),
    }

@app.post("/api/v1/checkins", response_model=CheckInResponse, status_code=201)
def create_checkin(
    payload: CheckInCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
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
def list_checkins(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list(db.scalars(
        select(CheckIn).where(CheckIn.user_id == user.id).order_by(CheckIn.created_at.desc()).limit(100)
    ))

@app.delete("/api/v1/checkins/{checkin_id}", status_code=204)
def delete_checkin(
    checkin_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    item = db.scalar(select(CheckIn).where(CheckIn.id == checkin_id, CheckIn.user_id == user.id))
    if not item:
        raise HTTPException(status_code=404, detail="Check-in not found.")
    db.delete(item)
    db.commit()

@app.delete("/api/v1/account", status_code=204)
def delete_account(db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(user)
    db.commit()
