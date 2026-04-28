from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from db.mysql import get_db
from models.place import Place
from schemas.request import PlaceSearchRequest
from schemas.response import PlaceCardResponse
from services.place_service import get_filtered_place_ids
from services.rag_graph import run_rag

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
    1차: RDBMS에서 카테고리/지역/시간/태그 조건으로 필터링
    2차: ChromaDB 시맨틱 검색으로 랭킹
    """
    # 1차 필터링: 조건에 맞는 place_id 추출
    valid_place_ids = get_filtered_place_ids(db, request)

    if not valid_place_ids:
        return {"message": "조건에 맞는 장소가 없습니다.", "places": []}

    if not request.keyword:
        return {"message": "검색 완료", "places": [{"place_id": pid} for pid in valid_place_ids[:10]]}

    # 2차: Query Rewrite → ChromaDB 시맨틱 검색 → LLM 선별 (LangGraph RAG)
    result = run_rag(keyword=request.keyword, valid_ids=valid_place_ids)

    return {"message": "검색 완료", "places": result["places"], "ai_summary": result["ai_summary"]}
