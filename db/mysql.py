from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings

# echo=True로 설정하면 실행되는 실제 SQL 쿼리 출력
engine = create_engine(settings.DATABASE_URL, echo=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# API 엔드포인트에서 DB 세션을 주입받기 위한 의존성 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
