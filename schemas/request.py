from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, Field


class GoogleLoginRequest(BaseModel):
    """구글 로그인 시 프론트엔드에서 보낸 ID 토큰을 받기 위한 DTO"""

    id_token: str = Field(..., description="구글 OAuth2 인증 후 받은 id_token")


class UserProfileUpdateRequest(BaseModel):
    """닉네임 및 프로필 사진 업데이트 요청 (온보딩/수정용)"""

    nickname: Optional[str] = Field(None, min_length=2, max_length=20, description="변경할 닉네임")
    profile_image: Optional[str] = Field(None, description="선택한 프로필 이미지 URL")


class UserTagUpdateRequest(BaseModel):
    """선호 태그 선택/수정 요청"""

    tag_ids: List[int] = Field(..., description="유저가 선택한 선호 태그 ID 리스트")


class FavoriteCreate(BaseModel):
    """선호 장소 등록을 위한 요청 DTO"""

    place_id: int


class PlaceSearchRequest(BaseModel):
    # 검색어
    keyword: Optional[str] = Field(
        default=None, description="사용자가 입력한 검색어. 없을 경우 None"
    )

    # 카테고리
    category: Optional[str] = Field(default=None, description="검색할 장소의 대분류")

    # 지역
    regions: Optional[List[str]] = Field(
        default_factory=list, description="선택된 지역 목록. 비어있으면 대구 전체"
    )

    # 날짜 및 시간
    target_date: Optional[date] = Field(default=None, description="방문 예정 날짜")
    target_time: Optional[time] = Field(default=None, description="방문 예정 시간")

    # 태그
    tag_ids: Optional[List[int]] = Field(
        default_factory=list, description="선택된 선호 태그의 ID 목록"
    )
