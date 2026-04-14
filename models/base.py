from sqlalchemy import BigInteger, Column, ForeignKey, Integer, Table
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# 다대다(N:M) 연관 테이블 정의
place_tags = Table(
    "Place_Tags",
    Base.metadata,
    Column(
        "place_id", BigInteger, ForeignKey("Places.place_id", ondelete="CASCADE"), primary_key=True
    ),
    Column("tag_id", Integer, ForeignKey("Tags.tag_id", ondelete="CASCADE"), primary_key=True),
)

user_preferred_tags = Table(
    "User_Preferred_Tags",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("Tags.tag_id", ondelete="CASCADE"), primary_key=True),
)
