from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, user_preferred_tags


class User(Base):
    __tablename__ = "Users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(50))
    refresh_token: Mapped[Optional[str]] = mapped_column(String(255))
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    profile_image: Mapped[Optional[str]] = mapped_column(String(255))

    # Relationships
    preferred_tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary=user_preferred_tags, back_populates="preferring_users"
    )
    search_histories: Mapped[List["SearchHistory"]] = relationship(
        "SearchHistory", back_populates="user", cascade="all, delete-orphan"
    )
    favorite_places: Mapped[List["FavoritePlace"]] = relationship(
        "FavoritePlace", back_populates="user", cascade="all, delete-orphan"
    )
