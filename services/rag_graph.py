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
from typing import TypedDict

# 직접 실행 시 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import END, StateGraph
from openai import OpenAI

from core.config import settings
from db.chroma import get_chroma_client

# ── 상수 ──────────────────────────────────────────────────────────────────────

COLLECTION_NAME = "place_reviews"
EMBED_MODEL     = "text-embedding-3-small"
CHAT_MODEL      = "gpt-4o-mini"
N_CANDIDATES    = 20

# ── OpenAI 싱글톤 ──────────────────────────────────────────────────────────────

_openai: OpenAI | None = None


def _client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai


# ── GraphState ────────────────────────────────────────────────────────────────

class PlaceRAGState(TypedDict):
    keyword    : str         # 원본 사용자 입력 (불변)
    question   : str         # rewrite 이후 최적화된 검색 쿼리
    valid_ids  : list[int]   # MySQL 1차 필터 결과 (입력으로 주입)
    candidates : list[dict]  # ChromaDB retrieve 결과 (상위 N개)
    results    : list[dict]  # 최종 추천 결과


# ── 시스템 프롬프트 ───────────────────────────────────────────────────────────

_REWRITE_SYSTEM = """당신은 장소 추천 검색 전문가입니다.
사용자의 자연어 질문을 벡터 검색에 최적화된 간결한 문장으로 재작성하세요.

재작성 시 아래 요소를 추출하여 명시적으로 포함하세요.
- 장소 유형 (카페, 식당, 공원 등)
- 방문 목적 (공부, 식사, 데이트, 모임 등)
- 동반자 유형 (혼자, 친구, 커플, 가족 등)
- 분위기·조건 키워드 (조용한, 넓은, 뷰가 좋은, 주차 가능 등)
- 가격대 (가성비, 합리적, 프리미엄 등)

규칙:
- 한 문장으로만 출력하세요.
- 설명이나 부연 없이 재작성된 질문만 출력하세요.
- 원래 질문의 의도를 유지하세요."""


# ── 노드 ─────────────────────────────────────────────────────────────────────

def _node_rewrite(state: PlaceRAGState) -> PlaceRAGState:
    """구어체 키워드 → 벡터 검색 최적화 문장"""
    keyword = state["keyword"]
    resp = _client().chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user",   "content": keyword},
        ],
        temperature=0,
    )
    question = resp.choices[0].message.content.strip()
    return {"question": question}


def _node_retrieve(state: PlaceRAGState) -> PlaceRAGState:
    """ChromaDB 시맨틱 검색 (valid_ids 범위 내)"""
    question  = state["question"]
    valid_ids = state["valid_ids"]

    if not valid_ids:
        return {"candidates": []}

    embedding = (
        _client().embeddings
        .create(model=EMBED_MODEL, input=[question])
        .data[0].embedding
    )

    n_query = min(N_CANDIDATES, len(valid_ids))
    collection = get_chroma_client().get_collection(name=COLLECTION_NAME)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_query,
        where={"place_id": {"$in": [str(pid) for pid in valid_ids]}},
        include=["metadatas", "documents", "distances"],
    )

    candidates = [
        {
            "place_id"  : int(m["place_id"]),
            "category"  : m.get("category", ""),
            "tags"      : [t for t in m.get("tags", "").split(",") if t],
            "summary"   : doc,
            "similarity": round(1 - dist, 4),
        }
        for m, doc, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        )
    ]

    return {"candidates": candidates}


def _node_generate(state: PlaceRAGState) -> PlaceRAGState:
    """LLM이 후보 중 최적 장소 선별 + 추천 이유 생성"""
    question   = state["question"]
    candidates = state["candidates"]
    n_results  = 10

    context = "\n".join(
        f"- place_id: {p['place_id']} | 카테고리: {p['category']} | "
        f"태그: {','.join(p['tags'])} | 요약: {p['summary'][:200]}"
        for p in candidates
    )

    json_format = '{"places": [{"place_id": 정수, "reason": "추천 이유 한 문장"}]}'
    prompt = (
        f'사용자 검색어: "{question}"\n\n'
        f"다음은 조건에 맞는 장소 목록입니다:\n{context}\n\n"
        f"위 장소 중 검색어와 가장 관련성 높은 최대 {n_results}개를 골라, "
        f"각각 한 줄 추천 이유를 작성하세요.\n"
        f"완벽한 일치가 없더라도 후보 중 가장 적합한 장소를 반드시 선택하세요.\n"
        f"반드시 place_id 값을 그대로 사용하고, 아래 JSON 형식으로만 응답하세요:\n{json_format}"
    )

    resp = _client().chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    ranked = json.loads(resp.choices[0].message.content).get("places", [])
    candidate_map = {p["place_id"]: p for p in candidates}

    results = []
    for item in ranked[:n_results]:
        pid = int(item["place_id"])
        if pid in candidate_map:
            results.append({**candidate_map[pid], "reason": item["reason"]})

    return {"results": results}


def _node_no_result(state: PlaceRAGState) -> PlaceRAGState:
    """후보가 없을 때 빈 결과 반환"""
    return {"results": []}


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

def run_rag(keyword: str, valid_ids: list[int]) -> list[dict]:
    """
    MySQL 1차 필터 결과(valid_ids)를 받아 RAG 파이프라인 실행.
    반환: [{"place_id", "category", "tags", "summary", "similarity", "reason"}, ...]
    """
    if not keyword or not valid_ids:
        return []

    initial: PlaceRAGState = {
        "keyword"   : keyword,
        "question"  : keyword,
        "valid_ids" : valid_ids,
        "candidates": [],
        "results"   : [],
    }

    final = _graph.invoke(initial)
    return final["results"]


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
    from services.place_service import get_filtered_place_ids
    from schemas.request import PlaceSearchRequest

    def _run_test(keyword: str, category: str | None = None, regions: list[str] | None = None):
        print(f"\n{'='*65}")
        print(f"  키워드  : {keyword}")
        print(f"  카테고리: {category or '전체'}")
        print(f"  지역    : {regions or '전체'}")
        print(f"{'='*65}")

        db = SessionLocal()
        try:
            # ── MySQL 1차 필터 ──────────────────────────────────────────
            req = PlaceSearchRequest(
                keyword=keyword,
                category=category,
                regions=regions or [],
            )
            valid_ids = get_filtered_place_ids(db, req)
        finally:
            db.close()

        print(f"\n[1단계] MySQL 1차 필터 → {len(valid_ids)}개")
        if valid_ids:
            print(f"  예시: {valid_ids[:5]} ...")
        else:
            print("  → 조건에 맞는 장소 없음. 종료.")
            return

        # ── RAG 파이프라인 ───────────────────────────────────────────────
        print(f"\n[2~4단계] RAG 파이프라인 실행 중 ...")

        # 중간 상태를 출력하려면 그래프를 stream으로 실행
        initial: PlaceRAGState = {
            "keyword"   : keyword,
            "question"  : keyword,
            "valid_ids" : valid_ids,
            "candidates": [],
            "results"   : [],
        }

        state = initial.copy()
        for step in _graph.stream(initial):
            node_name = next(iter(step))
            node_out  = step[node_name]

            if node_name == "rewrite":
                print(f"\n  [rewrite]")
                print(f"    원본  : {keyword}")
                print(f"    재작성: {node_out.get('question', '')}")
                state.update(node_out)

            elif node_name == "retrieve":
                candidates = node_out.get("candidates", [])
                print(f"\n  [retrieve] 후보 {len(candidates)}개")
                for c in candidates:
                    print(f"    {c['place_id']} | {c['category']} | 유사도 {c['similarity']} | {c['tags']}")
                state.update(node_out)

            elif node_name == "generate":
                print(f"\n  [generate] LLM 추천 선별 완료")
                state.update(node_out)

            elif node_name == "no_result":
                print(f"\n  [no_result] 유효한 후보 없음")
                state.update(node_out)

        # ── 최종 결과 출력 ──────────────────────────────────────────────
        results = state.get("results", [])
        print(f"\n{'─'*65}")
        print(f"최종 추천 {len(results)}개\n")
        for i, place in enumerate(results, 1):
            print(f"  [{i}] place_id  : {place['place_id']}")
            print(f"      카테고리  : {place['category']}")
            print(f"      태그      : {place['tags']}")
            print(f"      유사도    : {place['similarity']}")
            print(f"      추천 이유 : {place.get('reason', '-')}")
            print(f"      요약      : {place['summary'][:80]}...")
            print()

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

    _run_test(
        keyword="피규어가 잔뜩 있어서 볼게 가득한 카페",
        category="cafe",
    )