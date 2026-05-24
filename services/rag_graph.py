"""
LangGraph 기반 Place RAG 파이프라인

MySQL 1차 필터로 걸러진 valid_ids를 받아 후처리를 수행한다.

그래프 흐름:
  rewrite → retrieve → (candidates 있으면) generate → END
                     → (candidates 없으면) no_result → END

기존 ai_service.py / place_router.py 를 건드리지 않고,
run_rag() 함수만 외부에 노출한다.
"""

import sys
import os

# Windows 터미널 한글 출력 보장 (import 전에 먼저 설정)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import json
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

# 직접 실행 시 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import END, StateGraph
from openai import OpenAI

from core.config import settings
from db.chroma import get_chroma_client

# ── 상수 ──────────────────────────────────────────────────────────────────────

COLLECTION_NAME      = "place_reviews"
EMBED_MODEL          = "text-embedding-3-small"
CHAT_MODEL           = "gpt-4o-mini"
N_CANDIDATES         = 20

# ── OpenAI 싱글톤 ──────────────────────────────────────────────────────────────

_openai: OpenAI | None = None


def _client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

_INTERNAL_KEYS = frozenset({"matched_primary", "total_primary", "matched_secondary", "summary", "is_name_match"})


def _match_type(p: dict) -> str:
    """후보 dict로부터 match_type 문자열 결정 (name_match > exact > relevant > curated)"""
    if p.get("is_name_match"):
        return "name_match"
    mp = p.get("matched_primary", 0)
    tp = p.get("total_primary", 0)
    if tp > 0 and mp == tp:
        return "exact"
    if mp > 0 or p.get("matched_secondary", 0) > 0:
        return "relevant"
    return "curated"


# ── GraphState ────────────────────────────────────────────────────────────────

class PlaceRAGState(TypedDict):
    keyword            : str        # 원본 사용자 입력 (불변)
    question           : str        # rewrite 이후 최적화된 검색 쿼리
    primary_keywords   : list[str]  # 반드시 보유해야 할 핵심 아이템 (rewrite 단계 추출)
    secondary_keywords : list[str]  # 있으면 좋은 부가 아이템 (rewrite 단계 추출)
    exclusion_keywords : list[str]  # 주력 메뉴·특색이면 추천 불가 (알레르기·기피 재료 등)
    name_match_ids     : list[int]  # 가게 이름이 키워드와 일치하는 장소 ID (1순위 배치)
    embedding          : list[float] # rewrite와 병렬로 미리 계산된 임베딩
    valid_ids          : list[int]  # MySQL 1차 필터 결과 (입력으로 주입)
    candidates         : list[dict] # ChromaDB retrieve 결과 (상위 N개)
    results            : list[dict] # 최종 추천 결과
    ai_summary         : str        # 전체 추천 결과에 대한 AI 요약
    weather_info       : dict       # 날씨 정보 (temperature, condition) — 없으면 {}
    visit_context      : dict       # 방문 조건 (target_date, target_time, category) — 없으면 {}


# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

# 태그 목록 (DB Tags 테이블 기준 — 태그 추가 시 함께 갱신)
_AVAILABLE_TAGS = (
    "COMMON: 데이트, 소개팅, 친목/모임, 단체, 기념일, 가성비, 뷰맛집, 로컬맛집, "
    "인스타감성, 야외/테라스, 이색체험, 반려동물동반, 조용한, 활기찬, 아늑한, "
    "로맨틱한, 힙한/트렌디, 고급스러운, 레트로/빈티지\n"
    "CAFE: 혼카, 공부/독서\n"
    "RESTAURANT: 한식, 양식, 일식, 중식, 분식, 주점/안주, 뷔페, 혼밥, 가족외식\n"
    "ATTRACTION: 자연/풍경, 역사/유적, 문화/전시, 테마파크/놀이, 시장/쇼핑, "
    "아이와함께, 부모님과, 연인데이트, 나홀로여행, 우정여행, 학습/체험, "
    "야경명소, 인생샷/포토존, 산책, 힐링/휴식, 액티비티, 로컬감성, 등산/트레킹, "
    "고즈넉한, 여유로운, 이색적인, 신비로운, 깔끔한/현대적인"
)

_REWRITE_SYSTEM = f"""당신은 장소 추천 검색 전문가입니다.
사용자의 자연어 질문을 분석하여 아래 JSON 형식으로 응답하세요.

{{
  "question": "벡터 검색에 최적화된 한 문장",
  "primary_keywords": ["사용자가 가장 원하는 핵심 아이템 — 반드시 있어야 하는 것"],
  "secondary_keywords": ["부가 메뉴·음식·음료 또는 문맥에 맞는 태그명"],
  "exclusion_keywords": ["절대 포함하면 안 되는 음식·재료·특성 — 없으면 빈 배열"]
}}

question 작성 규칙:
- 장소 유형 (카페, 식당, 공원, 박물관 등), 방문 목적, 동반자 유형, 분위기 키워드 포함
- 관광지 검색 시 유형 (자연/풍경, 역사/유적, 문화/전시 등) 명시
- 가격대 언급 시 (가성비, 프리미엄 등) 포함
- 그룹 내 식이 제한(채식, 알레르기 등)이 있는 경우 "채식과 육류를 함께 제공하는" 같이 수용 범위를 명시
- 한 문장으로만 작성

primary_keywords 작성 규칙:
- 사용자가 이 검색을 하는 핵심 이유 — 반드시 충족돼야 하는 것
- 특정 메뉴·음식·경험(브런치, 카이막 등) 또는 available_tags 중 검색의 주목적인 것(소개팅, 공부/독서 등) 포함 가능
- 그룹 내 식이 제한이 있는 경우, 가장 제약이 강한 조건(채식주의자, 알레르기 등)을 primary로 — 그 조건을 못 맞추면 선택지가 없기 때문
- 예: "카이막에 도전하고 싶은데 커피도 맛있는 카페" → ["카이막"]
- 예: "소개팅 장소, 대화 이어지면 브런치도 먹고 싶어" → ["소개팅", "브런치"]
- 예: "카공하기 좋은 조용한 카페" → ["공부/독서"]  (available_tags에서 핵심 목적)
- 예: "채식주의자 + 고기 원하는 사람 혼재" → ["채식"] (채식 메뉴 보유가 핵심 제약)
- 단순 분위기·장소 유형은 제외 (조용한, 아늑한 등은 secondary로)
- 없으면 빈 배열 []

secondary_keywords 작성 규칙:
- ① primary 외에 함께 언급된 구체적 메뉴·음식·음료
- ② 아래 available_tags 중 사용자의 문맥(분위기·동반자)과 겹치는 태그명 (primary에 없는 것)
- ①②를 합쳐서 secondary_keywords 배열에 담음
- 그룹 내 식이 요구가 서로 다른 경우(채식+고기, 알레르기+일반식 혼재 등), "뷔페"를 secondary에 추가 — 각자 선택 가능해 모두를 커버할 수 있기 때문
- 예: "여자친구랑 카이막과 커피가 맛있는 카페" → ["커피", "데이트", "로맨틱한", "아늑한"]
- 예: "소개팅, 브런치 가능한 카페, 너무 비싸면 부담" → ["아늑한", "가성비"]
- 예: "카공하기 좋은 조용한 카페" → ["혼카", "조용한"]
- 예: "채식주의자 + 고기 원하는 사람 혼재 회식" → ["뷔페", "친목/모임", "단체"]
- 태그는 반드시 아래 available_tags 목록에서만 선택 (목록에 없는 단어 생성 금지)
- 없으면 빈 배열 []

exclusion_keywords 작성 규칙:
- 사용자가 명시한 알레르기 유발 식품·재료 (해산물, 견과류, 유제품, 글루텐 등) 추출
- 명시적 기피 음식·재료 (고수, 내장, 특정 재료 등) 추출
- 추출 기준: 이 항목이 장소의 주력 메뉴이거나 주된 특색이라면 추천하면 안 되는 것
- 단순 취향·분위기(조용한, 격식 등)는 포함하지 말 것
- 예: "해산물 알레르기 있는 팀원이 있어" → ["해산물"]
- 예: "견과류 알레르기 있고 유제품 못 먹어" → ["견과류", "유제품"]
- 없으면 빈 배열 []

available_tags:
{_AVAILABLE_TAGS}"""


# ── 노드 ─────────────────────────────────────────────────────────────────────

def _node_rewrite(state: PlaceRAGState) -> PlaceRAGState:
    """구어체 키워드 → 벡터 검색 최적화 문장 + 핵심 아이템 키워드 추출
    - embedding은 rewrite LLM 호출과 병렬로 원본 키워드로 미리 계산"""
    keyword = state["keyword"]

    def _do_rewrite():
        return _client().chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user",   "content": keyword},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

    def _do_embed():
        return (
            _client().embeddings
            .create(model=EMBED_MODEL, input=[keyword])
            .data[0].embedding
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        rewrite_future = executor.submit(_do_rewrite)
        embed_future   = executor.submit(_do_embed)
        resp      = rewrite_future.result()
        embedding = embed_future.result()

    try:
        raw = json.loads(resp.choices[0].message.content)
    except Exception:
        raw = {}

    question           = raw.get("question", keyword).strip() or keyword
    primary_keywords   = raw.get("primary_keywords", [])
    secondary_keywords = raw.get("secondary_keywords", [])
    exclusion_keywords = raw.get("exclusion_keywords", [])

    return {
        "question"          : question,
        "primary_keywords"  : primary_keywords,
        "secondary_keywords": secondary_keywords,
        "exclusion_keywords": exclusion_keywords,
        "embedding"         : embedding,
    }


def _node_retrieve(state: PlaceRAGState) -> PlaceRAGState:
    """ChromaDB 시맨틱 검색 + 아이템 텍스트 직접 검색 (valid_ids 범위 내)"""
    question  = state["question"]
    valid_ids = state["valid_ids"]

    if not valid_ids:
        return {"candidates": []}

    embedding = state.get("embedding") or []
    if not embedding:
        embedding = (
            _client().embeddings
            .create(model=EMBED_MODEL, input=[question])
            .data[0].embedding
        )

    try:
        collection = get_chroma_client().get_collection(name=COLLECTION_NAME)
    except Exception:
        return {"candidates": []}

    where_ids  = {"place_id": {"$in": [str(pid) for pid in valid_ids]}}

    def _to_candidate(m: dict, doc: str, dist: float,
                       matched_primary: int = 0, total_primary: int = 0,
                       matched_secondary: int = 0) -> dict:
        return {
            "place_id"        : int(m["place_id"]),
            "category"        : m.get("category", ""),
            "tags"            : [t for t in m.get("tags", "").split(",") if t],
            "summary"         : doc,
            "similarity"      : round(1 - dist, 4),
            "matched_primary" : matched_primary,
            "total_primary"   : total_primary,
            "matched_secondary": matched_secondary,
        }

    def _search_keywords(keywords: list[str], match_map: dict[int, set[str]]):
        """키워드 목록으로 ChromaDB 텍스트 검색 — match_map에 매칭 토큰 누적"""
        for kw in keywords:
            try:
                res = collection.query(
                    query_embeddings=[embedding],
                    n_results=min(10, len(valid_ids)),
                    where=where_ids,
                    where_document={"$contains": kw},
                    include=["metadatas", "documents", "distances"],
                )
                for m, doc, dist in zip(
                    res["metadatas"][0], res["documents"][0], res["distances"][0]
                ):
                    pid = int(m["place_id"])
                    match_map.setdefault(pid, set()).add(kw)
                    if pid not in token_meta_map:
                        token_meta_map[pid] = (m, doc, dist)
            except Exception:
                pass

    # 1) primary / secondary 키워드별 텍스트 직접 검색
    primary_kws   = state.get("primary_keywords") or []
    secondary_kws = state.get("secondary_keywords") or []
    total_primary = len(primary_kws)

    primary_match  : dict[int, set[str]] = {}
    secondary_match: dict[int, set[str]] = {}
    token_meta_map : dict[int, tuple]    = {}

    _search_keywords(primary_kws,   primary_match)
    _search_keywords(secondary_kws, secondary_match)

    # 2) 시맨틱 검색
    try:
        n_query = min(N_CANDIDATES, len(valid_ids))
        results  = collection.query(
            query_embeddings=[embedding],
            n_results=n_query,
            where=where_ids,
            include=["metadatas", "documents", "distances"],
        )
        semantic_list = [
            _to_candidate(m, doc, dist,
                          matched_primary=len(primary_match.get(int(m["place_id"]), set())),
                          total_primary=total_primary,
                          matched_secondary=len(secondary_match.get(int(m["place_id"]), set())))
            for m, doc, dist in zip(
                results["metadatas"][0],
                results["documents"][0],
                results["distances"][0],
            )
        ]
    except Exception:
        semantic_list = []

    # 3) 병합: 텍스트 매칭 장소 먼저, 이후 시맨틱 전용 (중복 제거)
    all_matched_pids = set(primary_match.keys()) | set(secondary_match.keys())
    token_candidates = [
        _to_candidate(m, doc, dist,
                      matched_primary=len(primary_match.get(pid, set())),
                      total_primary=total_primary,
                      matched_secondary=len(secondary_match.get(pid, set())))
        for pid, (m, doc, dist) in token_meta_map.items()
    ]
    seen       = set(all_matched_pids)
    candidates = list(token_candidates)
    for p in semantic_list:
        if p["place_id"] not in seen:
            seen.add(p["place_id"])
            candidates.append(p)

    # 4) 이름 직접 매칭 장소: ChromaDB에서 명시적으로 가져와 맨 앞에 배치
    name_match_ids_raw   = state.get("name_match_ids") or []
    valid_set            = set(valid_ids)
    name_match_ids_valid = [pid for pid in name_match_ids_raw if pid in valid_set]
    if name_match_ids_valid:
        nm_where = {"place_id": {"$in": [str(pid) for pid in name_match_ids_valid]}}
        try:
            nm_res = collection.query(
                query_embeddings=[embedding],
                n_results=len(name_match_ids_valid),
                where=nm_where,
                include=["metadatas", "documents", "distances"],
            )
            nm_candidates = []
            for m, doc, dist in zip(
                nm_res["metadatas"][0], nm_res["documents"][0], nm_res["distances"][0]
            ):
                pid = int(m["place_id"])
                c = _to_candidate(m, doc, dist,
                                  matched_primary=len(primary_match.get(pid, set())),
                                  total_primary=total_primary,
                                  matched_secondary=len(secondary_match.get(pid, set())))
                c["is_name_match"] = True
                nm_candidates.append(c)
            nm_pids    = {c["place_id"] for c in nm_candidates}
            candidates = nm_candidates + [c for c in candidates if c["place_id"] not in nm_pids]
        except Exception:
            pass

    # 5) exclusion_keywords: summary에 기피 키워드가 포함된 후보 제거
    exclusion_kws = state.get("exclusion_keywords") or []
    if exclusion_kws:
        candidates = [
            c for c in candidates
            if not any(kw in c["summary"] for kw in exclusion_kws)
        ]

    return {"candidates": candidates}


def _node_generate(state: PlaceRAGState) -> PlaceRAGState:
    """LLM이 후보 중 최적 장소 선별 + 전체 추천 요약 생성"""
    question           = state["question"]
    candidates         = state["candidates"]
    primary_kws        = state.get("primary_keywords") or []
    secondary_kws      = state.get("secondary_keywords") or []
    n_results          = 10

    _PRIORITY = {"name_match": -1, "exact": 0, "relevant": 1, "curated": 2}
    _LABELS   = {
        "name_match": " [NAME_MATCH: 이름 직접 일치]",
        "exact":      " [EXACT: 검색 아이템 실제 보유]",
        "relevant":   " [RELEVANT: 키워드 언급됨]",
        "curated":    " [CURATED: 취향 기반 선별]",
    }
    sorted_candidates = sorted(candidates, key=lambda p: _PRIORITY[_match_type(p)])

    context = "\n".join(
        f"- place_id: {p['place_id']} | 카테고리: {p['category']} | "
        f"태그: {','.join(p['tags'])} | 요약: {p['summary'][:200]}"
        + _LABELS[_match_type(p)]
        for p in sorted_candidates
    )

    # 방문 조건 한 줄 구성 (날짜·카테고리·날씨)
    visit_context = state.get("visit_context", {})
    _DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
    visit_parts = []
    if visit_context.get("target_date"):
        d = visit_context["target_date"]
        visit_parts.append(f"{d.strftime('%Y-%m-%d')}({_DAY_KR[d.weekday()]}요일)")
    if visit_context.get("category"):
        visit_parts.append(f"선호 카테고리: {visit_context['category']}")

    weather_info = state.get("weather_info", {})
    weather_context = ""
    if weather_info and "error" not in weather_info:
        cond = weather_info.get("condition", "")
        temp = weather_info.get("temperature")
        temp_str = f"{temp}°C" if temp is not None else "알수없음"
        visit_parts.append(f"날씨: {cond} {temp_str}")
        if cond in ["비", "눈"]:
            weather_context = " → 실내 장소를 우선 추천하세요."
        elif cond in ["맑음"] and temp is not None and float(temp) >= 25:
            weather_context = " → 더운 날씨이므로 에어컨이 있는 실내 또는 시원한 장소를 우선하세요."
        elif cond in ["맑음"] and temp is not None and float(temp) <= 5:
            weather_context = " → 추운 날씨이므로 따뜻한 실내 장소를 우선하세요."

    visit_line = f"\n방문 조건: {', '.join(visit_parts)}{weather_context}\n" if visit_parts else ""

    # primary/secondary/exclusion 키워드를 프롬프트에 명시
    primary_str   = ", ".join(primary_kws)   if primary_kws   else "없음"
    secondary_str = ", ".join(secondary_kws) if secondary_kws else "없음"
    kw_line = (
        f"핵심 아이템(primary, 반드시 보유): {primary_str}\n"
        f"부가 아이템(secondary, 있으면 좋음): {secondary_str}\n"
    )

    json_format = (
        '{"places": [{"place_id": 정수}], '
        '"summary": "선택된 장소들을 왜 이 사용자에게 추천하는지 실질적인 이유를 2-3문장으로 설명"}'
    )
    prompt = (
        f'사용자 검색어: "{question}"\n'
        f"{kw_line}"
        f"{visit_line}\n"
        f"다음은 조건에 맞는 장소 목록입니다:\n{context}\n\n"
        f"위 장소 중 검색어와 가장 관련성 높은 최대 {n_results}개를 골라 places에 담고, "
        f"선호 카테고리와 날씨 조건도 함께 고려하세요.\n"
        f"summary 작성 규칙:\n"
        f"- [NAME_MATCH] 장소: 검색어와 이름이 직접 일치합니다. 반드시 places 첫 번째에 포함하고, 장소 특징을 중심으로 서술하세요.\n"
        f"- [EXACT] 장소: primary 아이템({primary_str})이 리뷰에서 실제로 확인된 곳입니다. 보유 사실을 명확히 언급하세요.\n"
        f"- [RELEVANT] 장소: primary({primary_str}) 보유 여부는 리뷰에서 확인되지 않았습니다. "
        f"절대 보유한다고 단정하지 말고, '다양한 메뉴 구성으로 선택 가능성이 있습니다' 같은 가능성 표현을 쓰세요.\n"
        f"- [CURATED] 장소: 아무 아이템도 없지만 사용자 태그·분위기에 맞게 선별된 곳입니다.\n"
        f"위 구분을 지키면서 날씨·카테고리 등 반영 요소를 포함해 2-3문장으로 작성하세요.\n"
        f"- 장소 이름은 절대 언급하지 마세요. 분위기·특징·추천 이유만 설명하세요.\n"
        f"순서 규칙: [NAME_MATCH] → [EXACT] → [RELEVANT] → [CURATED] 순으로 places 배열에 배치하세요.\n"
        f"반드시 place_id 값을 그대로 사용하고, 아래 JSON 형식으로만 응답하세요:\n{json_format}"
    )

    resp = _client().chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    try:
        raw = json.loads(resp.choices[0].message.content)
    except Exception:
        raw = {}

    ranked     = raw.get("places", [])
    ai_summary = raw.get("summary", "")

    candidate_map = {p["place_id"]: p for p in candidates}

    results = []
    for item in ranked[:n_results]:
        try:
            pid = int(item["place_id"])
        except (KeyError, ValueError, TypeError):
            continue
        if pid in candidate_map:
            results.append(candidate_map[pid])

    # LLM이 아무것도 선택하지 않았으면 유사도 상위 후보를 그대로 반환
    if not results:
        results = sorted_candidates[:n_results]

    return {"results": results, "ai_summary": ai_summary}


def _node_no_result(state: PlaceRAGState) -> PlaceRAGState:
    """후보가 없을 때 빈 결과 반환"""
    return {"results": [], "ai_summary": ""}


# ── 조건부 엣지 ───────────────────────────────────────────────────────────────

def _route_after_retrieve(state: PlaceRAGState) -> str:
    return "generate" if state["candidates"] else "no_result"


# ── 그래프 컴파일 ─────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    wf = StateGraph(PlaceRAGState)

    wf.add_node("rewrite",   _node_rewrite)
    wf.add_node("retrieve",  _node_retrieve)
    wf.add_node("generate",  _node_generate)
    wf.add_node("no_result", _node_no_result)

    wf.set_entry_point("rewrite")
    wf.add_edge("rewrite", "retrieve")
    wf.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {"generate": "generate", "no_result": "no_result"},
    )
    wf.add_edge("generate",  END)
    wf.add_edge("no_result", END)

    return wf.compile()


_graph = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def run_rag(
    keyword: str,
    valid_ids: list[int],
    weather_info: dict | None = None,
    visit_context: dict | None = None,
    name_match_ids: list[int] | None = None,
) -> dict:
    """
    MySQL 1차 필터 결과(valid_ids)를 받아 RAG 파이프라인 실행.
    weather_info: {"temperature": float, "condition": str} — 없으면 None
    visit_context: {"target_date": date, "target_time": time, "category": str} — 없으면 None
    반환: {"places": [{"place_id", "category", "tags", "similarity"}, ...], "ai_summary": "..."}
    """
    if not keyword or not valid_ids:
        return {"places": [], "ai_summary": ""}

    initial: PlaceRAGState = {
        "keyword"           : keyword,
        "question"          : keyword,
        "primary_keywords"  : [],
        "secondary_keywords": [],
        "exclusion_keywords": [],
        "name_match_ids"    : name_match_ids or [],
        "embedding"         : [],
        "valid_ids"         : valid_ids,
        "candidates"        : [],
        "results"           : [],
        "ai_summary"        : "",
        "weather_info"      : weather_info or {},
        "visit_context"     : visit_context or {},
    }

    try:
        final = _graph.invoke(initial)
    except Exception:
        return {"places": [], "ai_summary": ""}

    places = []
    for p in final["results"]:
        place = {k: v for k, v in p.items() if k not in _INTERNAL_KEYS}
        place["match_type"] = _match_type(p)
        places.append(place)
    return {"places": places, "ai_summary": final["ai_summary"]}


# ── 테스트 (직접 실행 시) ─────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    # SQLAlchemy 관계 해소를 위해 모든 모델 선로드
    import models.user               # noqa: F401
    import models.history_and_event  # noqa: F401
    import models.tag                # noqa: F401
    import models.place              # noqa: F401

    from db.mysql import SessionLocal
    from services.place_service import get_filtered_place_ids, get_name_match_ids
    from services.landmarks import find_landmark
    from schemas.request import PlaceSearchRequest

    def _run_test(
        keyword: str,
        category: str | None = None,
        regions: list[str] | None = None,
        tag_ids: list[int] | None = None,
        weather_info: dict | None = None,
        visit_context: dict | None = None,
        ref_lat: float | None = None,   # 직접 좌표 지정 (랜드마크 자동 감지보다 우선)
        ref_lng: float | None = None,
        radius_km: float = 0.71,
    ):
        print(f"\n{'='*65}")
        print(f"  키워드  : {keyword}")
        print(f"  카테고리: {category or '전체'}")
        print(f"  지역    : {regions or '전체'}")
        if tag_ids:
            print(f"  선호태그: tag_ids={tag_ids}")
        if weather_info:
            print(f"  날씨    : {weather_info.get('condition')} {weather_info.get('temperature')}°C")
        if visit_context:
            _DAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
            vc = visit_context
            d = vc.get("target_date")
            from datetime import date as _date
            today = _date.today()
            if d:
                diff = (d - today).days
                label = {0: "오늘", 1: "내일", 2: "모레"}.get(diff, f"{diff}일 후" if diff > 0 else f"{-diff}일 전")
                print(f"  방문날짜: {d.strftime('%Y-%m-%d')}({_DAY_KR[d.weekday()]}요일) ← {label}")
        print(f"{'='*65}")

        db = SessionLocal()
        try:
            # ── MySQL 1차 필터 ──────────────────────────────────────────
            vc = visit_context or {}

            # 좌표 결정: 직접 지정 > 랜드마크 자동 감지
            if ref_lat is not None and ref_lng is not None:
                final_lat, final_lng = ref_lat, ref_lng
                print(f"  위치 직접 지정: 반경 {radius_km}km 필터 적용 ({final_lat}, {final_lng})")
            else:
                coords = find_landmark(keyword)
                if coords:
                    final_lat, final_lng = coords
                    print(f"  위치 감지: 반경 {radius_km}km 필터 적용 ({final_lat}, {final_lng})")
                else:
                    final_lat, final_lng = None, None

            # 지역 필터와 위치 필터 충돌 경고
            if regions and final_lat is not None:
                print(f"  [경고] regions={regions} 와 위치 필터가 AND 조건으로 적용됩니다. 교집합이 없으면 결과 0건.")

            req = PlaceSearchRequest(
                keyword=keyword,
                category=category,
                regions=regions or [],
                tag_ids=tag_ids or [],
                target_date=vc.get("target_date"),
                target_time=vc.get("target_time"),
                ref_lat=final_lat,
                ref_lng=final_lng,
                radius_km=radius_km,
            )
            valid_ids      = get_filtered_place_ids(db, req)
            name_match_ids = get_name_match_ids(db, keyword, valid_ids)
        finally:
            db.close()

        print(f"\n[1단계] MySQL 1차 필터 → {len(valid_ids)}개")
        if valid_ids:
            print(f"  예시: {valid_ids[:5]} ...")
        else:
            print("  → 조건에 맞는 장소 없음. 종료.")
            return
        if name_match_ids:
            print(f"  이름 매칭: place_ids={name_match_ids}")

        # ── TOURIST_SPOT: RAG 실행 → 부족하면 선호태그 풀 랜덤 → 전체 랜덤 채움 ──
        if category == "TOURIST_SPOT":
            print(f"\n[TOURIST_SPOT] RAG 실행 후 부족하면 랜덤으로 채움")

            result = run_rag(
                keyword=keyword,
                valid_ids=valid_ids,
                weather_info=weather_info,
                visit_context={"category": category},
                name_match_ids=name_match_ids,
            )

            import random as _random
            from models.place import Place as _Place
            from sqlalchemy.orm import joinedload as _jl

            places = result["places"]
            existing_ids = {p["place_id"] for p in places}

            # 선호태그 풀(valid_ids)에서 랜덤으로 채우기
            if len(places) < 10:
                remaining_valid = [pid for pid in valid_ids if pid not in existing_ids]
                remaining = 10 - len(places)
                if remaining_valid:
                    sample_ids = _random.sample(remaining_valid, min(remaining, len(remaining_valid)))
                    db2 = SessionLocal()
                    try:
                        rows = db2.query(_Place).options(_jl(_Place.tags)).filter(
                            _Place.place_id.in_(sample_ids)
                        ).all()
                    finally:
                        db2.close()
                    for p in rows:
                        places.append({
                            "place_id": p.place_id, "category": p.category,
                            "tags": [t.tag_name for t in p.tags],
                            "similarity": None, "match_type": "location",
                        })
                    existing_ids.update(p["place_id"] for p in places)

            # 전체 TOURIST_SPOT에서 남은 자리 채우기
            remaining = 10 - len(places)
            if remaining > 0:
                db2 = SessionLocal()
                try:
                    any_rows = db2.query(_Place).options(_jl(_Place.tags)).filter(
                        _Place.category == "TOURIST_SPOT",
                        _Place.place_id.notin_(existing_ids),
                    ).all()
                finally:
                    db2.close()
                for p in _random.sample(any_rows, min(remaining, len(any_rows))):
                    places.append({
                        "place_id": p.place_id, "category": p.category,
                        "tags": [t.tag_name for t in p.tags],
                        "similarity": None, "match_type": "location",
                    })

            print(f"\n{'─'*65}")
            print(f"최종 추천 {len(places)}개\n")
            for i, p in enumerate(places, 1):
                print(f"  [{i}] place_id={p['place_id']}  [{p.get('match_type', 'curated')}]")
                print(f"      카테고리: {p.get('category')}")
                print(f"      태그    : {p.get('tags')}")
                print(f"      유사도  : {p.get('similarity')}")
                print()
            print(f"AI 요약\n  {result.get('ai_summary', '')}")
            return

        # ── 이름 매칭 시 RAG 건너뜀 (place_router.py search_places 동일 로직) ──
        if name_match_ids:
            print(f"\n[NAME_MATCH] 이름 직접 매칭 → RAG 없이 DB에서 즉시 반환")
            db2 = SessionLocal()
            try:
                from models.place import Place as _Place
                from sqlalchemy.orm import joinedload as _jl
                places_raw = db2.query(_Place).options(_jl(_Place.tags)).filter(
                    _Place.place_id.in_(name_match_ids)
                ).all()
            finally:
                db2.close()
            print(f"\n{'─'*65}")
            print(f"최종 추천 {len(places_raw)}개  [name_match]\n")
            for i, p in enumerate(places_raw, 1):
                print(f"  [{i}] place_id  : {p.place_id}  [name_match]")
                print(f"      이름      : {p.name}")
                print(f"      카테고리  : {p.category}")
                print(f"      태그      : {[t.tag_name for t in p.tags]}")
                print()
            return

        # ── RAG 파이프라인 ───────────────────────────────────────────────
        print(f"\n[2~4단계] RAG 파이프라인 실행 중 ...")

        # 중간 상태를 출력하려면 그래프를 stream으로 실행
        initial: PlaceRAGState = {
            "keyword"           : keyword,
            "question"          : keyword,
            "primary_keywords"  : [],
            "secondary_keywords": [],
            "exclusion_keywords": [],
            "name_match_ids"    : name_match_ids,
            "embedding"         : [],
            "valid_ids"         : valid_ids,
            "candidates"        : [],
            "results"           : [],
            "ai_summary"        : "",
            "weather_info"      : weather_info or {},
            "visit_context"     : visit_context or {},
        }

        state = initial.copy()
        for step in _graph.stream(initial):
            node_name = next(iter(step))
            node_out  = step[node_name]

            if node_name == "rewrite":
                print(f"\n  [rewrite]")
                print(f"    원본        : {keyword}")
                print(f"    재작성      : {node_out.get('question', '')}")
                print(f"    primary     : {node_out.get('primary_keywords', [])}")
                print(f"    secondary   : {node_out.get('secondary_keywords', [])}")
                print(f"    exclusion   : {node_out.get('exclusion_keywords', [])}")
                state.update(node_out)

            elif node_name == "retrieve":
                candidates = node_out.get("candidates", [])
                print(f"\n  [retrieve] 후보 {len(candidates)}개")
                for c in candidates:
                    mp = c.get("matched_primary", 0)
                    tp = c.get("total_primary", 0)
                    ms = c.get("matched_secondary", 0)
                    if c.get("is_name_match"):
                        mark = " ★NAME_MATCH"
                    elif tp > 0 and mp == tp:
                        mark = f" ★EXACT(primary {mp}/{tp})"
                    elif mp > 0:
                        mark = f" ★RELEVANT(primary {mp}/{tp})"
                    elif ms > 0:
                        mark = f" ★RELEVANT(secondary)"
                    else:
                        mark = ""
                    print(f"    {c['place_id']} | {c['category']} | 유사도 {c['similarity']} | {c['tags']}{mark}")
                state.update(node_out)

            elif node_name == "generate":
                print(f"\n  [generate] LLM 추천 선별 완료")
                state.update(node_out)

            elif node_name == "no_result":
                print(f"\n  [no_result] 유효한 후보 없음")
                state.update(node_out)

        # ── 최종 결과 출력 ──────────────────────────────────────────────
        results    = state.get("results", [])
        ai_summary = state.get("ai_summary", "")
        print(f"\n{'─'*65}")
        print(f"최종 추천 {len(results)}개\n")
        for i, place in enumerate(results, 1):
            print(f"  [{i}] place_id  : {place['place_id']}  [{_match_type(place)}]")
            print(f"      카테고리  : {place['category']}")
            print(f"      태그      : {place['tags']}")
            print(f"      유사도    : {place['similarity']}")
            print(f"      요약      : {place['summary'][:80]}...")
            print()
        print(f"AI 요약\n  {ai_summary}")

    # ── 테스트 케이스 ────────────────────────────────────────────────────────
    # _run_test(
    #     keyword="혼자 공부하기 좋은 조용한 카페",
    #     category="cafe",
    # )

    # _run_test(
    #     keyword="가성비 좋은 혼밥 가능한 한식 맛집",
    #     category="restaurant",
    # )

    # _run_test(
    #     keyword="아늑한 플레이스의 망고 빙수 맛집",
    #     category="cafe",
    # )

    # _run_test(
    #     keyword="별도의 룸이 있어서 상견레 하기 좋을 프라이빗하고 조용한 식당",
    #     category="restaurant",
    # )

    # _run_test(
    #     keyword="카이막을 먹고싶어",
    #     category="cafe",
    # )

    from datetime import date, time

    # ── 기존 테스트 ───────────────────────────────────────────────────────────
    # _run_test(
    #     keyword="여자친구랑 처음 카이막에 도전하는데 커피랑 카이막이 맛있는 카페를 추천해줘",
    #     category="cafe",
    #     tag_ids=[39, 53, 47, 54],   # 데이트, 아늑한, 인스타감성, 로맨틱한
    #     weather_info={"condition": "맑음", "temperature": 22},
    #     visit_context={"category": "카페", "target_date": date(2026, 5, 27)},
    #     regions=["중구"]
    # )


    # [6] 좌표 직접 지정 — DB 장소 좌표 또는 임의 좌표로 주변 검색
    # 예: 수성못 좌표(35.8523, 128.6318) 반경 1km 내 카페
    # _run_test(
    #     keyword="분위기 좋은 카페",
    #     category="cafe",
    #     ref_lat=35.8285,   # 수성못 위도
    #     ref_lng=128.6172,  # 수성못 경도
    #     radius_km=1.0,
    # )

    # [7] 충돌 확인 — regions=수성구 + 동대구역 좌표 → 교집합 ≈ 0
    # _run_test(
    #     keyword="동대구역 근처 식당",
    #     category="restaurant",
    #     regions=["수성구"],   # 동대구역(동구)과 수성구는 겹치지 않음 → 결과 0건 예상
    # )

    # ── 꼬인 테스트 케이스 ────────────────────────────────────────────────────

    # [1] 카공 — 조용함 vs 스페셜티 감성, 눈치 없이 오래 앉기
    # _run_test(
    #     keyword=(
    #         "카공하러 가는 건데 진짜 집중은 잘 안 해도 돼. "
    #         "근데 너무 시끄러우면 집중 안 된다는 핑계 못 대니까 적당히 조용했으면 하고, "
    #         "커피는 산미 없는 거 마시고 싶은데 스페셜티 감성은 있으면 좋겠어. "
    #         "아이스 아메리카노 한 잔으로 3-4시간 버텨도 눈치 안 줬으면."
    #     ),
    #     category="cafe",
    #     tag_ids=[1, 2, 51, 55],     # 혼카, 공부/독서, 조용한, 힙한/트렌디
    #     weather_info={"condition": "맑음", "temperature": 28},
    #     visit_context={"category": "카페", "target_date": date(2026, 5, 22)},
    # )

    # [2] 팀 회식 — 채식주의자 + 해산물 알레르기 + 고기파 혼재
    # _run_test(
    #     keyword=(
    #         "팀 회식인데 채식주의자 한 명, 해산물 알레르기 한 명, "
    #         "나머지 여섯은 고기 실컷 먹고 싶어 하는 상황이야. "
    #         "코스 요리처럼 격식 있는 건 싫고 회식 특유의 어색함 좀 깨줄 수 있는 분위기면 좋겠어."
    #     ),
    #     category="restaurant",
    #     tag_ids=[41, 42, 52, 44, 5],  # 친목/모임, 단체, 활기찬, 가성비, 양식
    # )

    # [3] 소개팅 — 상대 모름, 가격 애매, 브런치 가능, 인스타 오버는 싫음
    # _run_test(
    #     keyword=(
    #         "소개팅 장소 정해야 하는데 상대가 어떤 사람인지 하나도 몰라. "
    #         "너무 비싸면 부담스럽고 너무 캐주얼하면 성의 없어 보이고. "
    #         "대화 이어지면 밥도 먹을 수 있게 브런치 되는 곳이면 좋겠는데, "
    #         "인스타 감성 넘치는 데는 좀 오글거려."
    #     ),
    #     category="cafe",
    #     tag_ids=[40, 53, 44],         # 소개팅, 아늑한, 가성비
    #     weather_info={"condition": "맑음", "temperature": 20},
    #     visit_context={"category": "카페", "target_date": date(2026, 5, 24)},
    # )

    # [4] 야간 혼카 — 밤 10시, 혼자인데 외롭지 않은 애매한 분위기
    # _run_test(
    #     keyword=(
    #         "밤 10시 넘어서 혼자 가도 자연스러운 카페인데, "
    #         "너무 조용해서 내 숨소리 들리는 분위기는 싫어. "
    #         "디저트 하나 시켜놓고 멍 때릴 수 있는데, 혼자인 게 눈에 띄지 않는 곳."
    #     ),
    #     category="cafe",
    #     tag_ids=[1, 55, 52],          # 혼카, 힙한/트렌디, 활기찬
    #     weather_info={"condition": "맑음", "temperature": 16},
    #     visit_context={
    #         "category": "카페",
    #         "target_date": date(2026, 5, 25),
    #         "target_time": time(22, 0),
    #     },
    # )

   
    # _run_test(
    #     keyword=(
    #         "동대구역 근처 밤 9시 넘어서 운영하는 맛집"
    #     ),
    #     category="restaurant",
    #     tag_ids=[44],
    #     weather_info={"condition": "맑음", "temperature": 16},
    #     visit_context={
    #         "target_date": date(2026, 5, 25),
    #         "target_time": time(21, 0),
    #     },
    # )

    # [이름 검색] 가게 이름 직접 검색 → NAME_MATCH 1순위 배치 확인
    # _run_test(
    #     keyword="요술밥상",
    #     category="restaurant",
    # )

    # _run_test(
    #     keyword="요술밥상과 비슷한 분위기의 식당",
    #     category="restaurant",
    # )

    # [관광명소] 가족 나들이
    _run_test(
        keyword="자연 풍경 명소 추천",
        category="TOURIST_SPOT",
        regions=["달성군"]
    )