from datetime import date, time, timedelta

from fastapi import APIRouter

from services.weather_service import get_current_weather, get_forecast_weather, get_mid_term_weather

router = APIRouter()


@router.get("/")
def get_main_weather():
    """
    메인 화면용 대구 전체 날씨를 조회
    """
    region_name = "대구전체"
    target_time = time(14, 0)
    today = date.today()

    weather_list = []

    for i in range(7):
        target_date = today + timedelta(days=i)

        if i == 0:
            w_info = get_current_weather(region_name)
        elif 1 <= i <= 2:
            w_info = get_forecast_weather(region_name, target_date, target_time)
        else:
            w_info = get_mid_term_weather(target_date, target_time)

        if w_info and "error" not in w_info:
            w_info["target_date"] = target_date.strftime("%Y-%m-%d")
            weather_list.append(w_info)
        else:
            weather_list.append(
                {
                    "region": region_name,
                    "target_date": target_date.strftime("%Y-%m-%d"),
                    "temperature": None,
                    "condition": "알수없음",
                    "error": w_info.get("error", "데이터를 불러오지 못했습니다.")
                    if w_info
                    else "오류 발생",
                }
            )

    return {"message": "날씨 조회 성공", "data": weather_list}


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
