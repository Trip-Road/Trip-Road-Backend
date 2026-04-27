from datetime import date, datetime, time, timedelta

import requests

from core.config import settings
from core.weather_utils import get_grid_by_region


def get_current_weather(region_name: str = "대구전체"):
    """
    기상청 초단기실황 API를 호출하여 현재 날씨를 반환
    """
    grid = get_grid_by_region(region_name)

    now = datetime.now()
    if now.minute < 40:
        now = now - timedelta(hours=1)

    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

    params = {
        "serviceKey": settings.WEATHER_API_KEY,
        "pageNo": "1",
        "numOfRows": "100",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": grid["nx"],
        "ny": grid["ny"],
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        # 기온(T1H), 강수형태(PTY), 습도(REH) 등 추출 로직
        weather_info = {"region": region_name, "temperature": None, "condition": "맑음"}
        for item in items:
            if item["category"] == "T1H":
                weather_info["temperature"] = float(item["obsrValue"])
            elif item["category"] == "PTY":
                # PTY: 0(없음), 1(비), 2(비/눈), 3(눈), 4(소나기)
                pty_code = item["obsrValue"]
                if pty_code == "1" or pty_code == "4":
                    weather_info["condition"] = "비"
                elif pty_code == "2" or pty_code == "3":
                    weather_info["condition"] = "눈"

        return weather_info
    else:
        return {"error": "날씨 정보를 불러오지 못했습니다."}


def get_forecast_weather(region_name: str, target_date: date, target_time: time):
    """
    기상청 단기예보 API를 호출하여 특정 날짜/시간의 날씨를 반환 (최대 3일 내외)
    """
    grid = get_grid_by_region(region_name)

    now = datetime.now()

    # 단기예보는 하루 8번 (02, 05, 08, 11, 14, 17, 20, 23시) 10분에 발표됨
    # 현재 시간 기준으로 가장 최근의 발표 시간을 계산
    if now.hour < 2 or (now.hour == 2 and now.minute < 10):
        # 새벽 2시 10분 이전이면 전날 23시 발표 자료를 사용
        base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
        base_time = "2300"
    else:
        base_date = now.strftime("%Y%m%d")
        valid_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        best_hour = 2
        for h in valid_hours:
            if now.hour > h or (now.hour == h and now.minute >= 10):
                best_hour = h
        base_time = f"{best_hour:02d}00"

    # 타겟 날짜와 시간을 기상청 API 포맷(YYYYMMDD, HH00)으로 변환
    target_date_str = target_date.strftime("%Y%m%d")
    target_time_str = target_time.strftime("%H00")

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

    params = {
        "serviceKey": settings.WEATHER_API_KEY,
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": grid["nx"],
        "ny": grid["ny"],
    }

    try:
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

            # 원하는 시간대의 날씨만 필터링
            weather_info = {"region": region_name, "temperature": None, "condition": "맑음"}

            # 하늘 상태 기본값 판별용
            sky_code = "1"

            found_data = False

            for item in items:
                if item["fcstDate"] == target_date_str and item["fcstTime"] == target_time_str:
                    found_data = True
                    category = item["category"]

                    if category == "TMP":
                        weather_info["temperature"] = float(item["fcstValue"])

                    elif category == "SKY":  # 하늘상태 (1: 맑음, 3: 구름많음, 4: 흐림)
                        sky_code = item["fcstValue"]
                        if sky_code == "3":
                            weather_info["condition"] = "구름많음"
                        elif sky_code == "4":
                            weather_info["condition"] = "흐림"

                    elif category == "PTY":  # 강수형태 (0: 없음, 1: 비, 2: 비/눈, 3: 눈, 4: 소나기)
                        pty_code = item["fcstValue"]
                        if pty_code in ["1", "4"]:
                            weather_info["condition"] = "비"
                        elif pty_code in ["2", "3"]:
                            weather_info["condition"] = "눈"

            # PTY(강수)가 0이면 SKY(하늘상태)를 따르고, 비나 눈이 오면 PTY 상태로 덮어씌워짐
            if not found_data:
                return {"error": "해당 날짜/시간의 예보 데이터가 아직 없거나 범위를 벗어났습니다."}

            return weather_info

        else:
            return {"error": f"날씨 정보를 불러오지 못했습니다. 상태 코드: {response.status_code}"}
    except Exception as e:
        return {"error": f"API 통신 오류: {e}"}


def get_mid_term_weather(target_date: date, target_time: time):
    """
    기상청 중기예보 API를 호출하여 3일 ~ 10일 뒤의 날씨와 기온을 반환
    대구광역시 기준 (기온: 11H10702, 육상/날씨: 11H10000)
    """
    now = datetime.now()

    # 중기예보는 매일 06시, 18시 두 번만 발표됨
    if now.hour < 6:
        base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
        base_time = "1800"
    elif now.hour < 18:
        base_date = now.strftime("%Y%m%d")
        base_time = "0600"
    else:
        base_date = now.strftime("%Y%m%d")
        base_time = "1800"

    # 타겟 날짜가 오늘로부터 며칠 뒤인지 계산 (3 ~ 10 사이)
    days_diff = (target_date - now.date()).days
    if days_diff < 3 or days_diff > 10:
        return {"error": "중기예보는 3일 후부터 10일 후까지만 조회가 가능합니다."}

    # 오전(Am)인지 오후(Pm)인지 판별 (8~10일차는 종일 예보라 Am/Pm 구분이 없음)
    time_suffix = "Am" if target_time.hour < 12 else "Pm"
    if days_diff >= 8:
        time_suffix = ""

    # API 1: 육상예보 (날씨 상태 - 맑음, 흐림, 비 등)
    # 11H10000 = 대구, 경상북도 지역 코드
    url_land = "http://apis.data.go.kr/1360000/MidFcstInfoService/getMidLandFcst"
    params_land = {
        "serviceKey": settings.WEATHER_API_KEY,
        "pageNo": "1",
        "numOfRows": "10",
        "dataType": "JSON",
        "tmFc": f"{base_date}{base_time}",
        "regId": "11H10000",
    }

    # API 2: 기온조회 (최저/최고 기온)
    # 11H10702 = 대구광역시 기온 코드
    url_temp = "http://apis.data.go.kr/1360000/MidFcstInfoService/getMidTa"
    params_temp = {
        "serviceKey": settings.WEATHER_API_KEY,
        "pageNo": "1",
        "numOfRows": "10",
        "dataType": "JSON",
        "tmFc": f"{base_date}{base_time}",
        "regId": "11H10702",
    }

    try:
        res_land = requests.get(url_land, params=params_land)
        res_temp = requests.get(url_temp, params=params_temp)

        weather_info = {"region": "대구전체", "temperature": None, "condition": "알수없음"}

        # 날씨 상태 추출 (wf3Am, wf3Pm, wf4Am ... wf8 등)
        if res_land.status_code == 200:
            land_items = (
                res_land.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
            )
            if land_items:
                wf_key = f"wf{days_diff}{time_suffix}"  # 예: wf3Am, wf4Pm
                condition_raw = land_items[0].get(wf_key, "맑음")

                # 기상청 텍스트(예: "구름많고 비")를 프론트엔드/AI 스펙에 맞게 정제
                if "비" in condition_raw or "소나기" in condition_raw:
                    weather_info["condition"] = "비"
                elif "눈" in condition_raw:
                    weather_info["condition"] = "눈"
                elif "흐림" in condition_raw:
                    weather_info["condition"] = "흐림"
                elif "구름" in condition_raw:
                    weather_info["condition"] = "구름많음"
                else:
                    weather_info["condition"] = "맑음"

        # 기온 추출 (taMin3, taMax3 ... taMin10, taMax10)
        # 중기예보는 특정 시간의 기온이 아니라 그 날의 최저/최고 기온만 제공
        # 오전이면 최저기온(Min), 오후면 최고기온(Max)을 대략적인 온도로 사용
        if res_temp.status_code == 200:
            temp_items = (
                res_temp.json().get("response", {}).get("body", {}).get("items", {}).get("item", [])
            )
            if temp_items:
                if target_time.hour < 12:
                    temp_key = f"taMin{days_diff}"
                else:
                    temp_key = f"taMax{days_diff}"

                temp_val = temp_items[0].get(temp_key)
                if temp_val is not None:
                    weather_info["temperature"] = float(temp_val)

        return weather_info
    except Exception as e:
        return {"error": f"중기예보 통신 오류: {e}"}
