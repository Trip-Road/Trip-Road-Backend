서버 실행 방법  

1. 환경 변수 설정

    프로젝트 최상위 폴더에 .env 파일 넣기

3. 터미널에서 아래 내용 실행

    python -m venv venv

    source venv\Scripts\activate  

    pip install -r requirements.txt  

4. 서버 실행

    uvicorn main:app --reload

API 주소: http://127.0.0.1:8000

Interactive API Docs (Swagger): http://127.0.0.1:8000/docs

---

## RAG 파이프라인

장소 검색 API(`POST /api/v1/places/search`)는 keyword가 있을 때 아래 LangGraph 기반 RAG 파이프라인을 통해 결과를 반환한다.

### 관련 파일

| 파일 | 역할 |
|---|---|
| `api/v1/place_router.py` | 검색 엔드포인트. MySQL 1차 필터 후 `run_rag()` 호출 |
| `services/place_service.py` | MySQL 1차 필터 로직 (`get_filtered_place_ids`) |
| `services/rag_graph.py` | LangGraph RAG 파이프라인 본체. 외부에 `run_rag()` 노출 |
| `db/chroma.py` | ChromaDB HttpClient 싱글톤 |

### 처리 흐름

```
POST /api/v1/places/search
        │
        ▼
[place_service] MySQL 1차 필터
  카테고리 / 지역 / 영업일·시간 / 태그 → valid_ids
        │
        │ keyword 없으면 valid_ids 상위 10개 그대로 반환
        │ keyword 있으면 ↓
        ▼
[rag_graph] LangGraph 파이프라인
  ┌─────────────────────────────────────────────┐
  │  rewrite   구어체 키워드 → 벡터 검색 최적화 문장  │
  │     ↓      (gpt-4o-mini, temperature=0)      │
  │  retrieve  ChromaDB 시맨틱 검색               │
  │            valid_ids 풀 안에서 유사도 상위 20개  │
  │     ↓                                        │
  │  generate  후보 중 최적 10개 선별 + 추천 이유     │
  │  (또는 no_result: 후보 없으면 빈 리스트 반환)    │
  └─────────────────────────────────────────────┘
        │
        ▼
  [{"place_id", "category", "tags", "summary", "similarity", "reason"}, ...]
```

### `run_rag()` 시그니처

```python
# services/rag_graph.py
def run_rag(keyword: str, valid_ids: list[int]) -> list[dict]:
    ...
```

- `keyword`: 사용자 입력 검색어 (내부에서 rewrite됨)
- `valid_ids`: MySQL 1차 필터로 걸러진 place_id 목록
- 반환: 최대 10개의 추천 장소 리스트

### 단독 테스트 실행

```bash
venv/Scripts/python services/rag_graph.py
```

실행하면 MySQL → ChromaDB → LLM 전체 파이프라인을 두 가지 케이스(카페/식당)로 테스트한다.
