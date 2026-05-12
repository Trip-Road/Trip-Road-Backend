from datetime import date

from fastapi import HTTPException
from sqlalchemy import extract
from sqlalchemy.orm import Session

from models.history_and_event import Event


def get_monthly_events(db: Session):
    """
    현재 날짜의 월을 기준으로 진행 중인 행사를 조회
    """
    today = date.today()
    current_month = today.month

    return (
        db.query(Event)
        .filter(
            extract("month", Event.start_date) <= current_month,
            extract("month", Event.end_date) >= current_month,
            Event.end_date >= today,
        )
        .all()
    )


def get_event_detail(db: Session, event_id: int):
    """
    특정 ID를 가진 행사의 상세 정보를 조회
    """
    event = db.query(Event).filter(Event.event_id == event_id).first()

    if not event:
        raise HTTPException(status_code=404, detail="해당 행사를 찾을 수 없습니다.")

    return event
