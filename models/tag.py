from typing import List

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, place_tags, user_preferred_tags


class Tag(Base):
    __tablename__ = "Tags"

    tag_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="태그명")
    tag_category: Mapped[str] = mapped_column(
        Enum("COMMON", "RESTAURANT", "CAFE", "ATTRACTION"), nullable=False, comment="태그 종류"
    )

    # Relationships
    places: Mapped[List["Place"]] = relationship(
        "Place", secondary=place_tags, back_populates="tags"
    )
    preferring_users: Mapped[List["User"]] = relationship(
        "User", secondary=user_preferred_tags, back_populates="preferred_tags"
    )
