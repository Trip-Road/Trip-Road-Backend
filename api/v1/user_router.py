from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.mysql import get_db
from models.tag import Tag
from models.user import User
from schemas.request import UserProfileUpdateRequest, UserTagUpdateRequest
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
    if request.profile_image:
        current_user.profile_image = request.profile_image

    # DB 저장
    db.commit()
    db.refresh(current_user)

    return current_user


@router.patch("/me/tags", response_model=UserResponse)
def update_user_tags(
    request: UserTagUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    유저가 선택한 취향 태그들을 저장
    """

    valid_tags = db.query(Tag).filter(Tag.tag_id.in_(request.tag_ids)).all()

    if len(valid_tags) != len(request.tag_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="존재하지 않는 태그 ID가 포함되어 있습니다.",
        )

    current_user.preferred_tags = valid_tags

    current_user.is_onboarded = True

    db.commit()
    db.refresh(current_user)

    return current_user
