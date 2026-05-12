from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from api.deps import get_current_user
from db.mysql import get_db
from models.history_and_event import SearchHistory
from models.place import Place
from models.user import User
from schemas.request import PlaceSearchRequest
from schemas.response import PlaceCardResponse, PlaceDetailResponse
from services.place_service import attach_place_info, get_filtered_place_ids, get_place_detail_info
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
def search_places(
    request: PlaceSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    1차: RDBMS에서 카테고리/지역/시간/태그 조건으로 필터링
    2차: ChromaDB 시맨틱 검색으로 랭킹
    """
    # 1차 필터링: 조건에 맞는 place_id 추출
    valid_place_ids = get_filtered_place_ids(db, request)

    if not valid_place_ids:
        return {"message": "조건에 맞는 장소가 없습니다.", "places": []}

    # 검색어 저장 및 관리
    if request.keyword:
        existing_history = (
            db.query(SearchHistory)
            .filter(
                SearchHistory.user_id == current_user.user_id,
                SearchHistory.keyword == request.keyword,
            )
            .first()
        )

    if existing_history:
        existing_history.created_at = datetime.now()
    else:
        new_history = SearchHistory(user_id=current_user.user_id, keyword=request.keyword)
        db.add(new_history)

    db.commit()

    user_histories = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.user_id)
        .order_by(desc(SearchHistory.created_at))
        .all()
    )

    if len(user_histories) > 10:
        for old_history in user_histories[10:]:
            db.delete(old_history)
        db.commit()

    if not request.keyword:
        return {
            "message": "검색 완료",
            "places": [{"place_id": pid} for pid in valid_place_ids[:10]],
        }

    # 2차: Query Rewrite → ChromaDB 시맨틱 검색 → LLM 선별 (LangGraph RAG)
    result = run_rag(keyword=request.keyword, valid_ids=valid_place_ids)

    places = attach_place_info(result["places"], db)
    return {"message": "검색 완료", "places": places, "ai_summary": result["ai_summary"]}


@router.get("/{place_id}", response_model=PlaceDetailResponse)
def get_place_detail(
    place_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    특정 장소의 상세 정보를 조회
    """
    detail = get_place_detail_info(db, place_id, current_user.user_id)

    if not detail:
        raise HTTPException(status_code=404, detail="장소를 찾을 수 없습니다.")

    return detail
