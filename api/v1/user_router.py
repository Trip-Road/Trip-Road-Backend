from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.mysql import get_db
from models.user import User
from schemas.request import UserProfileUpdateRequest
from schemas.response import UserResponse

router = APIRouter()


@router.patch("/me/profile", response_model=UserResponse)
def update_profile(
    request: UserProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    내 프로필을 수정
    """
    # 프론트엔드가 보낸 값만 선택적으로 업데이트
    if request.nickname:
        current_user.nickname = request.nickname
    if request.profile_image_url:
        current_user.profile_image_url = request.profile_image_url

    # DB 저장
    db.commit()
    db.refresh(current_user)

    return current_user
