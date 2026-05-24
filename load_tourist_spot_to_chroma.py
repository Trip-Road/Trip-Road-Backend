"""
crawling/output/tourist_spot/*.jsonl → ChromaDB 저장
- 기존 store_to_chroma.py와 동일 방식
- tourist_spot 전용 처리: 태그 # 제거, category → TOURIST_SPOT 정규화
"""

import json
import os
import sys
import uuid
from pathlib import Path

import chromadb
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

INPUT_DIR       = Path(r"C:\Users\wodnd\Downloads\crawling\output\tourist_spot")
COLLECTION_NAME = "place_reviews"
BATCH_SIZE      = 100
EMBED_MODEL     = "text-embedding-3-small"


def load_records(input_dir: Path) -> list[dict]:
    records = []
    for f in sorted(input_dir.glob("*.jsonl")):
        with open(f, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                # # 제거, category 정규화
                r["tags"]     = [t.lstrip("#") for t in r.get("tags", [])]
                r["category"] = "TOURIST_SPOT"
                records.append(r)
    return records


def get_stored_ids(collection) -> set[str]:
    result = collection.get(include=["metadatas"])
    return {m["place_id"] for m in result["metadatas"]}


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def main():
    api_key     = os.getenv("OPENAI_API_KEY")
    chroma_host = os.getenv("CHROMADB_HOST", "54.180.88.242")
    chroma_port = int(os.getenv("CHROMADB_PORT", 8001))

    chroma = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    collection = chroma.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"ChromaDB 연결 완료 | collection: {COLLECTION_NAME}")

    records = load_records(INPUT_DIR)
    print(f"전체 레코드: {len(records):,}개")

    stored_ids = get_stored_ids(collection)
    pending = [r for r in records if r["place_id"] not in stored_ids]
    print(f"이미 저장됨: {len(stored_ids):,}개 | 저장 예정: {len(pending):,}개")

    if not pending:
        print("모두 저장되어 있습니다.")
        print(f"총 문서 수: {collection.count():,}개")
        return

    openai_client = OpenAI(api_key=api_key)

    for i in tqdm(range(0, len(pending), BATCH_SIZE), desc="ChromaDB 저장 중"):
        batch = pending[i : i + BATCH_SIZE]
        texts = [r["summary"] for r in batch]

        embeddings = embed_texts(openai_client, texts)

        metadatas = [
            {
                "place_id":     r["place_id"],
                "category":     r["category"],
                "tags":         ",".join(r["tags"]),
                "data_quality": r.get("data_quality", ""),
                "review_count": r.get("review_count", 0),
            }
            for r in batch
        ]
        ids = [str(uuid.uuid4()) for _ in batch]

        collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

    print(f"\n완료! 총 문서 수: {collection.count():,}개")


if __name__ == "__main__":
    main()
