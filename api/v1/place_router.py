import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date as date_class
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from api.deps import get_current_user
from db.mysql import get_db
from models.history_and_event import FavoritePlace, SearchHistory
from models.place import Place
from models.tag import Tag
from models.user import User
from schemas.request import PlaceSearchRequest
from schemas.response import PlaceCardResponse, PlaceDetailResponse
from services.landmarks import find_landmark
from services.place_service import (
    attach_place_info,
    get_filtered_place_ids,
    get_name_match_ids,
    get_place_detail_info,
)
from services.rag_graph import run_rag
from services.weather_service import get_current_weather, get_forecast_weather, get_mid_term_weather


def _weather_to_keyword(weather_info: dict) -> str:
    """날씨 정보를 RAG 검색용 키워드로 변환"""
    cond = weather_info.get("condition", "")
    temp = weather_info.get("temperature")
    if cond in ["비", "눈"]:
        return f"{cond}오는 날 실내에서 즐길 수 있는 장소"
    if cond == "맑음":
        if temp is not None and float(temp) >= 25:
            return "더운 날씨 에어컨 시원한 실내 추천"
        if temp is not None and float(temp) <= 5:
            return "추운 날씨 따뜻한 실내 카페 추천"
        return "맑은 날 야외 나들이 추천 장소"
    return "오늘 날씨에 어울리는 대구 추천 장소"


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
    # keyword에서 랜드마크 감지 → 좌표 필터 자동 설정
    if request.keyword and request.ref_lat is None:
        coords = find_landmark(request.keyword)
        if coords:
            request = request.model_copy(update={"ref_lat": coords[0], "ref_lng": coords[1]})

    # 날씨 fetch 함수 (스레드에서 실행)
    def _fetch_weather():
        if not (request.target_date and request.target_time):
            return None
        region = request.regions[0] if request.regions else "대구전체"
        days_diff = (request.target_date - date_class.today()).days
        try:
            if days_diff == 0:
                return get_current_weather(region)
            elif 1 <= days_diff <= 2:
                return get_forecast_weather(region, request.target_date, request.target_time)
            elif 3 <= days_diff <= 10:
                return get_mid_term_weather(request.target_date, request.target_time)
        except Exception:
            pass
        return None

    # 1차 필터링(MySQL) + 날씨 조회 병렬 실행
    with ThreadPoolExecutor(max_workers=1) as executor:
        weather_future = executor.submit(_fetch_weather)
        valid_place_ids = get_filtered_place_ids(db, request)
        weather_info = weather_future.result()

    if not valid_place_ids:
        return {"message": "조건에 맞는 장소가 없습니다.", "places": []}

    user_fav_rows = (
        db.query(FavoritePlace.place_id).filter(FavoritePlace.user_id == current_user.user_id).all()
    )
    user_fav_ids = {row[0] for row in user_fav_rows}

    if not request.keyword:
        return {
            "message": "검색 완료",
            "places": [
                {"place_id": pid, "is_favorite": pid in user_fav_ids}
                for pid in valid_place_ids[:10]
            ],
        }

    # 검색어 저장 및 관리
    existing_history = (
        db.query(SearchHistory)
        .filter(
            SearchHistory.user_id == current_user.user_id,
            SearchHistory.keyword == request.keyword,
        )
        .first()
    )
    if existing_history:
        existing_history.created_at = datetime.now(timezone.utc)
    else:
        db.add(SearchHistory(user_id=current_user.user_id, keyword=request.keyword))
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

    # TOURIST_SPOT: 검색어로 RAG 실행 → 부족하면 선호태그 랜덤으로 채움
    if request.category == "TOURIST_SPOT":
        tag_ids = [tag.tag_id for tag in current_user.preferred_tags]
        name_match_ids = get_name_match_ids(db, request.keyword, valid_place_ids)
        visit_context = {"category": request.category}

        result = run_rag(
            keyword=request.keyword,
            valid_ids=valid_place_ids,
            weather_info=weather_info,
            visit_context=visit_context,
            name_match_ids=name_match_ids,
        )
        places = attach_place_info(result["places"], db, user_fav_ids)

        # 10개 미만이면 선호태그 포함 장소로 채우기
        if len(places) < 10:
            existing_ids = {p["place_id"] for p in places}
            remaining = 10 - len(places)
            fallback = []

            if tag_ids:
                tagged_rows = (
                    db.query(Place)
                    .options(joinedload(Place.tags))
                    .filter(
                        Place.place_id.in_(valid_place_ids),
                        Place.place_id.notin_(existing_ids),
                        Place.tags.any(Tag.tag_id.in_(tag_ids)),
                    )
                    .all()
                )
                for p in random.sample(tagged_rows, min(remaining, len(tagged_rows))):
                    fallback.append(
                        {
                            "place_id": p.place_id,
                            "name": p.name,
                            "category": p.category,
                            "tags": [t.tag_name for t in p.tags],
                            "similarity": None,
                            "image": p.image_url,
                            "match_type": "location",
                            "is_favorite": p.place_id in user_fav_ids,
                        }
                    )
                existing_ids.update(p["place_id"] for p in fallback)

            # 선호태그로도 모자라면 valid_place_ids 내 나머지 랜덤으로
            remaining = 10 - len(places) - len(fallback)
            if remaining > 0:
                any_rows = (
                    db.query(Place)
                    .options(joinedload(Place.tags))
                    .filter(
                        Place.place_id.in_(valid_place_ids),
                        Place.place_id.notin_(existing_ids),
                    )
                    .all()
                )
                for p in random.sample(any_rows, min(remaining, len(any_rows))):
                    fallback.append(
                        {
                            "place_id": p.place_id,
                            "name": p.name,
                            "category": p.category,
                            "tags": [t.tag_name for t in p.tags],
                            "similarity": None,
                            "image": p.image_url,
                            "match_type": "location",
                            "is_favorite": p.place_id in user_fav_ids,
                        }
                    )

            places.extend(fallback)

        return {
            "message": "검색 완료",
            "places": places,
            "ai_summary": result.get("ai_summary", ""),
        }

    # 2차: 이름 직접 매칭 확인 → 있으면 RAG 없이 즉시 반환
    name_match_ids = get_name_match_ids(db, request.keyword, valid_place_ids)
    if name_match_ids:
        places_raw = (
            db.query(Place)
            .options(joinedload(Place.tags))
            .filter(Place.place_id.in_(name_match_ids))
            .all()
        )
        places = [
            {
                "place_id": p.place_id,
                "name": p.name,
                "category": p.category,
                "tags": [t.tag_name for t in p.tags],
                "similarity": 1.0,
                "image": p.image_url,
                "match_type": "name_match",
                "is_favorite": p.place_id in user_fav_ids,
            }
            for p in places_raw
        ]
        return {"message": "검색 완료", "places": places, "ai_summary": ""}

    # 이름 매칭 없음 → Query Rewrite → ChromaDB 시맨틱 검색 → LLM 선별 (LangGraph RAG)
    visit_context = {
        "target_date": request.target_date,
        "target_time": request.target_time,
        "category": request.category,
    }
    result = run_rag(
        keyword=request.keyword,
        valid_ids=valid_place_ids,
        weather_info=weather_info,
        visit_context=visit_context,
    )

    places = attach_place_info(result["places"], db, user_fav_ids)
    return {"message": "검색 완료", "places": places, "ai_summary": result["ai_summary"]}


@router.get("/recommendations")
def get_recommendations(
    category: Optional[str] = Query(default=None, description="카페 | 음식점 | 관광명소"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    메인화면 추천 API
    - 사용자 최근 검색어 + 선호 태그 + 실시간 날씨를 종합하여 장소 추천
    - keyword 없고 날씨도 없으면 선호 태그 필터 결과만 반환
    """
    # 선호 태그 ID 목록
    tag_ids = [tag.tag_id for tag in current_user.preferred_tags]

    # 최근 검색어
    latest_history = (
        db.query(SearchHistory)
        .filter(SearchHistory.user_id == current_user.user_id)
        .order_by(desc(SearchHistory.created_at))
        .first()
    )
    keyword = latest_history.keyword if latest_history else None

    # 실시간 날씨
    try:
        weather_info = get_current_weather("대구전체")
        if "error" in weather_info:
            weather_info = None
    except Exception:
        weather_info = None

    # 1차 필터링 (선호 태그 + 카테고리)
    filter_request = PlaceSearchRequest(
        category=category,
        tag_ids=tag_ids if tag_ids else None,
    )
    valid_place_ids = get_filtered_place_ids(db, filter_request)

    if not valid_place_ids:
        return {"message": "조건에 맞는 장소가 없습니다.", "places": [], "ai_summary": ""}

    user_fav_rows = (
        db.query(FavoritePlace.place_id).filter(FavoritePlace.user_id == current_user.user_id).all()
    )
    user_fav_ids = {row[0] for row in user_fav_rows}

    # TOURIST_SPOT: keyword + 선호태그 활용, RAG 실행 후 부족하면 랜덤으로 채움
    if category == "TOURIST_SPOT":
        places = []
        ai_summary = ""

        # keyword 있으면 RAG로 최적 매칭 먼저
        if keyword:
            result = run_rag(
                keyword=keyword,
                valid_ids=valid_place_ids,
                weather_info=weather_info,
                visit_context={"category": category},
            )
            places = attach_place_info(result["places"], db, user_fav_ids)
            ai_summary = result.get("ai_summary", "")

        # 10개 미만이면 선호태그 풀(valid_place_ids)에서 랜덤으로 채우기
        if len(places) < 10:
            existing_ids = {p["place_id"] for p in places}
            remaining = 10 - len(places)
            fallback = []

            remaining_valid = [pid for pid in valid_place_ids if pid not in existing_ids]
            if remaining_valid:
                sample_ids = random.sample(remaining_valid, min(remaining, len(remaining_valid)))
                rows = (
                    db.query(Place)
                    .options(joinedload(Place.tags))
                    .filter(Place.place_id.in_(sample_ids))
                    .all()
                )
                for p in rows:
                    fallback.append(
                        {
                            "place_id": p.place_id,
                            "name": p.name,
                            "category": p.category,
                            "tags": [t.tag_name for t in p.tags],
                            "similarity": None,
                            "image": p.image_url,
                            "match_type": "location",
                            "is_favorite": p.place_id in user_fav_ids,
                        }
                    )
                existing_ids.update(p["place_id"] for p in fallback)

            # 선호태그 풀에서도 모자라면 전체 TOURIST_SPOT에서 랜덤
            remaining = 10 - len(places) - len(fallback)
            if remaining > 0:
                any_rows = (
                    db.query(Place)
                    .options(joinedload(Place.tags))
                    .filter(
                        Place.category == "TOURIST_SPOT",
                        Place.place_id.notin_(existing_ids),
                    )
                    .all()
                )
                for p in random.sample(any_rows, min(remaining, len(any_rows))):
                    fallback.append(
                        {
                            "place_id": p.place_id,
                            "name": p.name,
                            "category": p.category,
                            "tags": [t.tag_name for t in p.tags],
                            "similarity": None,
                            "image": p.image_url,
                            "match_type": "location",
                            "is_favorite": p.place_id in user_fav_ids,
                        }
                    )

            places.extend(fallback)

        return {"message": "추천 완료", "places": places, "ai_summary": ai_summary}

    # keyword 없고 날씨도 없으면 → 태그 필터 결과만 반환
    if not keyword and not weather_info:
        places_raw = (
            db.query(Place)
            .options(joinedload(Place.tags))
            .filter(Place.place_id.in_(valid_place_ids[:10]))
            .all()
        )
        places = [
            {
                "place_id": p.place_id,
                "name": p.name,
                "category": p.category,
                "tags": [t.tag_name for t in p.tags],
                "similarity": None,
                "image": p.image_url,
                "match_type": "location",
                "is_favorite": p.place_id in user_fav_ids,
            }
            for p in places_raw
        ]
        return {"message": "추천 완료", "places": places, "ai_summary": ""}

    # keyword 없고 날씨만 있으면 → 날씨 기반 키워드 자동 생성
    if not keyword and weather_info:
        keyword = _weather_to_keyword(weather_info)

    name_match_ids = get_name_match_ids(db, keyword, valid_place_ids) if keyword else []

    # 이름 직접 매칭 시: 해당 가게와 비슷한 장소 추천으로 전환
    if name_match_ids and keyword:
        matched_place = (
            db.query(Place)
            .options(joinedload(Place.tags))
            .filter(Place.place_id == name_match_ids[0])
            .first()
        )
        if matched_place:
            tags_str = ", ".join([t.tag_name for t in matched_place.tags])
            keyword = f"{keyword}과 비슷한 분위기의 {matched_place.category or ''}" + (
                f" (태그: {tags_str})" if tags_str else ""
            )
            valid_place_ids = [pid for pid in valid_place_ids if pid not in set(name_match_ids)]
        name_match_ids = []

    visit_context = {"category": category}
    result = run_rag(
        keyword=keyword,
        valid_ids=valid_place_ids,
        weather_info=weather_info,
        visit_context=visit_context,
        name_match_ids=name_match_ids,
    )

    places = attach_place_info(result["places"], db, user_fav_ids)
    return {"message": "추천 완료", "places": places, "ai_summary": result["ai_summary"]}


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
