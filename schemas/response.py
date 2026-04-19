from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class TagResponse(BaseModel):
    tag_id: int
    tag_name: str

    model_config = ConfigDict(from_attributes=True)


class PlaceCardResponse(BaseModel):
    """
    메인 홈 및 검색 결과 리스트에서 장소 카드를 그릴 때 사용하는 DTO
    """

    place_id: int
    name: str
    category: str
    region: str
    image_url: Optional[str] = None
    # 장소에 연결된 태그들 중 대표적인 것들만 포함
    tags: List[TagResponse] = []

    # SQLAlchemy 모델 객체를 Pydantic DTO로 자동 변환하기 위한 설정
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """자체 JWT 발급 응답"""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class UserResponse(BaseModel):
    """유저 정보 응답 (프로필 사진 및 온보딩 여부 포함)"""

    user_id: int
    nickname: Optional[str]
    profile_image: Optional[str] = None
    is_onboarded: bool = False

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    """로그인 최종 응답 (토큰 + 유저 기본 정보)"""

    tokens: TokenResponse
    user: UserResponse


class TagCategoryResponse(BaseModel):
    """
    프론트엔드에서 카테고리별로 묶어서 태그를 보여주기 위한 딕셔너리 구조
    """

    pass
