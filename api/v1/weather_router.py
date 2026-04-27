from datetime import date, time

from fastapi import APIRouter

from services.weather_service import get_current_weather, get_forecast_weather, get_mid_term_weather

router = APIRouter()


@router.get("/")
def get_main_weather():
    """
    메인 화면용 대구 전체 날씨를 조회
    """
    weather_data = get_current_weather("대구전체")
    return {"message": "날씨 조회 성공", "data": weather_data}


@router.get("/test/forecast")
def test_forecast_api(
    region_name: str = "대구전체", target_date: date = None, target_time: time = None
):
    """
    단기예보 테스트 API (1~2일 뒤 날짜를 입력)
    예시: target_date = 2024-05-15, target_time = 14:00:00
    """
    return get_forecast_weather(region_name, target_date, target_time)


@router.get("/test/mid-term")
def test_mid_term_api(target_date: date = None, target_time: time = None):
    """
    중기예보 테스트 API (3~10일 뒤 날짜를 입력)
    예시: target_date = 2024-05-20, target_time = 14:00:00
    """
    return get_mid_term_weather(target_date, target_time)
