DAEGU_GRID_MAP = {
    "대구전체": {"nx": 89, "ny": 90},  # 중구 기준 (메인화면용)
    "중구": {"nx": 89, "ny": 90},
    "동구": {"nx": 90, "ny": 91},
    "서구": {"nx": 88, "ny": 90},
    "남구": {"nx": 89, "ny": 90},
    "북구": {"nx": 89, "ny": 91},
    "수성구": {"nx": 89, "ny": 90},
    "달서구": {"nx": 88, "ny": 90},
    "달성군": {"nx": 86, "ny": 88},
    "군위군": {"nx": 88, "ny": 99},
}


def get_grid_by_region(region_name: str):
    return DAEGU_GRID_MAP.get(region_name, DAEGU_GRID_MAP["대구전체"])
