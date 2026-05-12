from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.mysql import get_db
from models.history_and_event import SearchHistory
from models.tag import Tag
from models.user import User
from schemas.request import UserProfileUpdateRequest, UserTagUpdateRequest
from schemas.response import SearchHistoryResponse, UserResponse

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


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    유저 레코드 및 연관된 데이터를 모두 삭제합니다.
    """
    db.delete(current_user)
    db.commit()

    return None


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    내 프로필 정보 조회
    현재 로그인한 유저의 닉네임, 프로필 이미지, 온보딩 상태, 선호 태그를 반환
    """

    return current_user


@router.get(
    "/me/search-histories", response_model=List[SearchHistoryResponse], summary="최근 검색어 조회"
)
def get_search_histories(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    현재 로그인한 유저의 최근 검색어 목록을 최신순으로 반환 (최대 10개)
    """
    histories = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.user_id)
        .order_by(desc(SearchHistory.created_at))
        .all()
    )

    return histories


@router.delete(
    "/me/search-histories/{history_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="특정 최근 검색어 삭제",
)
def delete_search_history(
    history_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    선택한 단일 최근 검색어를 삭제
    """
    history = (
        db.query(SearchHistory)
        .filter(
            SearchHistory.history_id == history_id, SearchHistory.user_id == current_user.user_id
        )
        .first()
    )

    if not history:
        raise HTTPException(status_code=404, detail="검색 기록을 찾을 수 없습니다.")

    db.delete(history)
    db.commit()

    return None


@router.delete(
    "/me/search-histories", status_code=status.HTTP_204_NO_CONTENT, summary="최근 검색어 전체 삭제"
)
def clear_all_search_histories(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    사용자의 최근 검색어를 모두 삭제
    """
    db.query(SearchHistory).filter(SearchHistory.user_id == current_user.user_id).delete()
    db.commit()

    return None
