from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.deps import get_current_user
from db.mysql import get_db
from models.history_and_event import FavoritePlace
from models.place import Place
from models.user import User
from schemas.request import FavoriteCreate
from schemas.response import PlaceCardResponse

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, summary="선호 장소 등록")
def add_favorite_place(
    req: FavoriteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    특정 장소를 사용자의 선호 장소로 추가
    """
    place = db.query(Place).filter(Place.place_id == req.place_id).first()
    if not place:
        raise HTTPException(status_code=404, detail="존재하지 않는 장소입니다.")

    existing_fav = (
        db.query(FavoritePlace)
        .filter(
            FavoritePlace.user_id == current_user.user_id, FavoritePlace.place_id == req.place_id
        )
        .first()
    )
    if existing_fav:
        raise HTTPException(status_code=400, detail="이미 선호 장소로 등록되었습니다.")

    new_fav = FavoritePlace(user_id=current_user.user_id, place_id=req.place_id)
    db.add(new_fav)
    db.commit()

    return {"message": "선호 장소로 등록되었습니다."}


@router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT, summary="선호 장소 삭제")
def remove_favorite_place(
    place_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    사용자의 선호 장소 목록에서 특정 장소를 삭제
    """
    fav = (
        db.query(FavoritePlace)
        .filter(FavoritePlace.user_id == current_user.user_id, FavoritePlace.place_id == place_id)
        .first()
    )

    if not fav:
        raise HTTPException(status_code=404, detail="선호 장소로 등록되지 않은 장소입니다.")

    db.delete(fav)
    db.commit()
    return None


@router.get("", response_model=List[PlaceCardResponse], summary="선호 장소 목록 조회")
def get_user_favorites(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    로그인한 사용자가 등록한 선호 장소 리스트를 최신순으로 조회
    """
    fav_places = (
        db.query(Place)
        .join(FavoritePlace, Place.place_id == FavoritePlace.place_id)
        .filter(FavoritePlace.user_id == current_user.user_id)
        .order_by(FavoritePlace.created_at.desc())
        .all()
    )

    result = []
    for place in fav_places:
        place_dict = {
            "place_id": place.place_id,
            "name": place.name,
            "category": place.category,
            "region": place.region,
            "image_url": place.image_url,
            "tags": place.tags,
            "is_favorite": True,
        }
        result.append(place_dict)

    return result
