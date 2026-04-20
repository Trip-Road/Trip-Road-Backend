from datetime import time
from typing import List, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, place_tags


class Place(Base):
    __tablename__ = "Places"

    place_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="플레이스 id"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="장소명")
    category: Mapped[Optional[str]] = mapped_column(String(50), comment="카테고리")
    region: Mapped[Optional[str]] = mapped_column(String(20), comment="구/군")
    address: Mapped[Optional[str]] = mapped_column(String(255), comment="상세 주소")
    business_hours: Mapped[Optional[str]] = mapped_column(Text, comment="영업시간 원본 텍스트")
    phone: Mapped[Optional[str]] = mapped_column(String(50), comment="전화번호")
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 8), comment="위도")
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(11, 8), comment="경도")
    image_url: Mapped[Optional[str]] = mapped_column(String(255), comment="장소 이미지 URL")
    review_summary: Mapped[Optional[str]] = mapped_column(Text, comment="AI 리뷰 요약")

    # Relationships
    operating_hours: Mapped[List["OperatingHour"]] = relationship(
        "OperatingHour", back_populates="place", cascade="all, delete-orphan"
    )
    tags: Mapped[List["Tag"]] = relationship("Tag", secondary=place_tags, back_populates="places")
    # favorited_by: Mapped[List["FavoritePlace"]] = relationship(
    #     "FavoritePlace", back_populates="place", cascade="all, delete-orphan"
    # )


class OperatingHour(Base):
    __tablename__ = "Operating_Hours"

    hour_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    place_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("Places.place_id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False, comment="1:월~7:일")
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, comment="정기휴무")
    open_time: Mapped[Optional[time]] = mapped_column(Time)
    close_time: Mapped[Optional[time]] = mapped_column(Time)
    break_start: Mapped[Optional[time]] = mapped_column(Time)
    break_end: Mapped[Optional[time]] = mapped_column(Time)
    last_order: Mapped[Optional[time]] = mapped_column(Time)

    place: Mapped["Place"] = relationship("Place", back_populates="operating_hours")

    __table_args__ = (Index("idx_operating_hours_day", "day_of_week", "is_closed"),)
