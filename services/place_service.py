from typing import List

from sqlalchemy.orm import Session

from models.place import Place
from models.tag import Tag
from schemas.request import PlaceSearchRequest


def attach_place_info(rag_places: list[dict], db: Session) -> list[dict]:
    """RAG 결과에 MySQL에서 조회한 name, image를 붙이고 summary를 제거한다."""
    if not rag_places:
        return []

    place_ids = [p["place_id"] for p in rag_places]
    rows = db.query(Place.place_id, Place.name, Place.image_url).filter(
        Place.place_id.in_(place_ids)
    ).all()
    info_map = {row.place_id: {"name": row.name, "image": row.image_url or None} for row in rows}

    result = []
    for p in rag_places:
        info = info_map.get(p["place_id"], {})
        result.append({
            "place_id" : p["place_id"],
            "name"     : info.get("name"),
            "category" : p["category"],
            "tags"     : p["tags"],
            "similarity": p["similarity"],
            "image"    : info.get("image"),
        })
    return result


def get_filtered_place_ids(db: Session, request: PlaceSearchRequest) -> List[int]:
    """
    사용자의 검색 조건을 바탕으로 RDBMS에서 1차 필터링을 수행하고
    조건에 부합하는 장소의 ID 리스트를 반환
    """

    # Place의 ID만 가져오는 기본 쿼리 시작
    query = db.query(Place.place_id)

    # 카테고리 필터
    if request.category:
        query = query.filter(Place.category == request.category)

    # 지역 필터
    if request.regions:
        query = query.filter(Place.region.in_(request.regions))

    # 선호 태그 필터
    # 요청된 태그 중 하나라도 포함하는 장소를 필터링 (OR 조건)
    if request.tag_ids:
        query = query.filter(Place.tags.any(Tag.tag_id.in_(request.tag_ids)))

    # # 방문 예정일 및 방문 시간 필터
    # if request.target_date or request.target_time:
    #     query = query.join(Place.operating_hours)

    #     #  방문 날짜 필터
    #     if request.target_date:
    #         target_day = request.target_date.weekday() + 1
    #         query = query.filter(
    #             OperatingHour.day_of_week == target_day, OperatingHour.is_closed == False
    #         )

    #     # 방문 시간 필터
    #     if request.target_time:
    #         t = request.target_time

    #         # 조건 A: 오픈 시간 <= 방문 시간 <= 마감 시간
    #         time_condition = and_(OperatingHour.open_time <= t, OperatingHour.close_time >= t)

    #         # 조건 B: 브레이크 타임이 설정되어 있지 않거나, 방문 시간이 브레이크 타임을 벗어날 것
    #         break_condition = or_(
    #             OperatingHour.break_start.is_(None),
    #             OperatingHour.break_end.is_(None),
    #             t < OperatingHour.break_start,
    #             t > OperatingHour.break_end,
    #         )

    #         # 조건 C: 라스트 오더 시간이 없거나, 방문 시간이 라스트 오더 이하일 것
    #         last_order_condition = or_(
    #             OperatingHour.last_order.is_(None), t <= OperatingHour.last_order
    #         )

    #         # 세 가지 조건이 모두 만족해야 함
    #         query = query.filter(time_condition, break_condition, last_order_condition)

    # 조인으로 인해 발생할 수 있는 중복 레코드를 제거하고 결과 추출
    result = query.distinct().all()

    return [row[0] for row in result]
