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
