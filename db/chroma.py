import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import settings

try:
    chroma_client = chromadb.HttpClient(
        host=settings.CHROMADB_HOST,
        port=settings.CHROMADB_PORT,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    # 연결 테스트를 위해 하트비트 요청 (연결 실패 시 예외 발생)
    chroma_client.heartbeat()
    print("ChromaDB 서버에 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"ChromaDB 서버 연결 실패: {e}")


def get_chroma_client():
    """
    API 의존성 주입이나 Service 레이어에서
    ChromaDB 클라이언트를 가져올 때 사용
    """
    return chroma_client
