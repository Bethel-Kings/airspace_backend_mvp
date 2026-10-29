from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    checkins: Mapped[list["CheckIn"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    reflections: Mapped[list["Reflection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class CheckIn(Base):
    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    before_score: Mapped[int] = mapped_column(Integer, nullable=False)
    after_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user: Mapped["User"] = relationship(back_populates="checkins")


class Reflection(Base):
    __tablename__ = "reflections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # The text the user vented / typed (stored only when the user opts in).
    source_text: Mapped[str] = mapped_column(String(12000), nullable=False)
    # The AI-generated response.
    ai_reply: Mapped[str] = mapped_column(String(4000), nullable=False)
    prompt_style: Mapped[str] = mapped_column(String(20), default="gentle", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user: Mapped["User"] = relationship(back_populates="reflections")
