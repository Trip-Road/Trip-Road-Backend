from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SearchHistory(Base):
    __tablename__ = "Search_Histories"

    history_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="search_histories")


class FavoritePlace(Base):
    __tablename__ = "Favorite_Places"

    favorite_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), nullable=False
    )
    place_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("Places.place_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="favorite_places")
    place: Mapped["Place"] = relationship("Place", back_populates="favorited_by")


class Event(Base):
    __tablename__ = "Events"

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255))
    start_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(DateTime, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (Index("idx_events_dates", "start_date", "end_date"),)
