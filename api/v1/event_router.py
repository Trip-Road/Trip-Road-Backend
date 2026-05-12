from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.mysql import get_db
from schemas.response import EventResponse
from services import event_service

router = APIRouter()


@router.get("", response_model=List[EventResponse], summary="이달의 행사 목록 조회")
def get_events(db: Session = Depends(get_db)):
    """
    대구 지역의 이번 달 행사 및 축제 리스트를 반환
    """
    return event_service.get_monthly_events(db)


@router.get("/{event_id}", response_model=EventResponse, summary="행사 상세 정보 조회")
def get_event(event_id: int, db: Session = Depends(get_db)):
    """
    행사 ID를 입력받아 상세 정보를 반환
    """
    return event_service.get_event_detail(db, event_id)
