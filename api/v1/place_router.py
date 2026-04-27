from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from db.mysql import get_db
from models.place import Place
from schemas.request import PlaceSearchRequest
from schemas.response import PlaceCardResponse
from services.place_service import get_filtered_place_ids

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
def search_places(request: PlaceSearchRequest, db: Session = Depends(get_db)):
    """
    검색 조건에 맞는 장소를 1차로 RDBMS에서 필터링한 후,
    AI 서비스로 넘기고 추천 받은 장소와 추천 이유를 반환(현재는 1차 필터링 반환)
    """

    # 조건에 맞는 장소 ID 리스트 추출
    valid_place_ids = get_filtered_place_ids(db, request)

    # 만약 1차 필터링 결과가 없다면 바로 빈 결과 반환
    if not valid_place_ids:
        return {"message": "조건에 맞는 장소가 없습니다.", "data": []}

    # -------------------------------------------------------------
    # (다음 단계) AI 파트 개발자를 위한 영역
    # 추출된 valid_place_ids와 request.keyword를 AIRecommendationService로 넘겨
    # ChromaDB 하이브리드 검색 및 LLM 추천 이유를 생성하도록 넘김
    #
    # 예시:
    # final_recommendations = ai_service.get_recommendations(
    #     keyword=request.keyword,
    #     valid_ids=valid_place_ids
    # )
    # -------------------------------------------------------------

    return {
        "message": "1차 필터링 완료",
        "filtered_place_count": len(valid_place_ids),
        "valid_place_ids": valid_place_ids,
    }
