from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from db.mysql import get_db
from models.place import Place
from schemas.request import PlaceSearchRequest
from schemas.response import PlaceCardResponse

router = APIRouter()


@router.get("/", response_model=List[PlaceCardResponse])
def get_places(db: Session = Depends(get_db)):
    """
    필터링/추천 로직이 적용될 표준 장소 목록 조회 API
    (현재는 DTO 적용 확인을 위해 전체 데이터를 반환)
    """
    places = db.query(Place).options(joinedload(Place.tags)).limit(10).all()

    return places


@router.post("/search")
async def search_places(request: PlaceSearchRequest):
    # request 객체를 PlaceService 또는 Repository로 넘겨서 DB 1차 필터링 시작
    # valid_place_ids = await place_service.get_filtered_place_ids(request)

    return {"message": "DTO 연동 성공!", "data": request.dict()}
