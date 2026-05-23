from __future__ import annotations

_LANDMARKS: list[dict] = [
    {"name": "동대구역",   "aliases": ["동대구", "동대구터미널", "대구동역", "신세계", "대구신세계", "신세계백화점"],         "lat": 35.8794, "lng": 128.6287},
    {"name": "대구역",     "aliases": ["서대구역", "대구기차역"],                     "lat": 35.8758, "lng": 128.5961},
    {"name": "동성로",     "aliases": ["중앙로", "대구중심가", "동성로거리"],          "lat": 35.8697, "lng": 128.5939},
    {"name": "반월당",     "aliases": ["반월당역", "대구백화점"],                      "lat": 35.8661, "lng": 128.5938},
    {"name": "수성못",     "aliases": ["수성유원지", "수성못유원지"],                  "lat": 35.8285, "lng": 128.6172},
    {"name": "두류공원",   "aliases": ["두류", "이월드", "대구놀이공원"],              "lat": 35.8508, "lng": 128.5587},
    {"name": "앞산",       "aliases": ["앞산공원", "앞산케이블카"],                    "lat": 35.8310, "lng": 128.5735},
    {"name": "팔공산",     "aliases": ["팔공", "갓바위", "팔공산케이블카"],            "lat": 35.9887, "lng": 128.6934},
    {"name": "서문시장",   "aliases": ["서문", "서문시장골목"],                        "lat": 35.8694, "lng": 128.5807},
    {"name": "김광석다리", "aliases": ["방천시장", "김광석길"],                        "lat": 35.8608, "lng": 128.6059},
    {"name": "대구공항",   "aliases": ["공항", "대구국제공항"],                        "lat": 35.8981, "lng": 128.6376},
    {"name": "칠성시장",   "aliases": ["칠성", "칠성동시장"],                          "lat": 35.8760, "lng": 128.6040},
    {"name": "대구수목원", "aliases": ["수목원", "달서수목원"],                         "lat": 35.8015, "lng": 128.5196},
    {"name": "비슬산",     "aliases": ["비슬", "비슬산자연휴양림"],                    "lat": 35.6932, "lng": 128.4706},
    {"name": "대구스타디움", "aliases": ["대구월드컵경기장", "대구경기장"],            "lat": 35.8316, "lng": 128.6873},
    {"name": "서대구역",    "aliases": ["서대구KTX", "서대구KTX역"],                  "lat": 35.8814, "lng": 128.5401},
    {"name": "경북대학교",  "aliases": ["경북대", "경대"],                             "lat": 35.8927, "lng": 128.6092},
    {"name": "계명대학교",  "aliases": ["계명대"],                                     "lat": 35.8518, "lng": 128.4859},
    {"name": "범어역",      "aliases": ["범어", "수성구청역"],                          "lat": 35.8585, "lng": 128.6248},
    {"name": "엑스코",      "aliases": ["EXCO", "대구엑스코", "대구전시컨벤션센터"],   "lat": 35.9051, "lng": 128.6123},
    {"name": "라이온즈파크","aliases": ["대구야구장", "삼성라이온즈파크"],              "lat": 35.8411, "lng": 128.6812},
]


def find_landmark(keyword: str) -> tuple[float, float] | None:
    """키워드에서 랜드마크를 감지해 (lat, lng)를 반환. 없으면 None."""
    for lm in _LANDMARKS:
        if lm["name"] in keyword:
            return lm["lat"], lm["lng"]
        for alias in lm["aliases"]:
            if alias in keyword:
                return lm["lat"], lm["lng"]
    return None
