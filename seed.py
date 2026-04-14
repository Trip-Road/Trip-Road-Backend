from db.mysql import SessionLocal  # noqa: I001
from models.place import Place
from models.tag import Tag

import models.user
import models.history_and_event  # noqa: F401


def seed_database():
    db = SessionLocal()
    try:
        # 1. 기존 데이터가 있는지 확인 (중복 실행 방지)
        if db.query(Place).first():
            print("💡 이미 데이터가 존재합니다. Seeding을 건너뜁니다.")
            return

        print("🌱 데이터 Seeding을 시작합니다...")

        # 2. 초기 태그 데이터 생성
        tag1 = Tag(tag_name="데이트하기 좋은", tag_category="COMMON")
        tag2 = Tag(tag_name="가성비", tag_category="RESTAURANT")
        tag3 = Tag(tag_name="조용한", tag_category="CAFE")
        tag4 = Tag(tag_name="사진맛집", tag_category="ATTRACTION")

        db.add_all([tag1, tag2, tag3, tag4])
        db.commit()  # 태그를 먼저 DB에 저장하여 ID를 발급받음

        # 3. 초기 장소(Place) 데이터 생성
        place1 = Place(
            name="대구 수성못 카페 뷰",
            category="CAFE",
            region="수성구",
            address="대구광역시 수성구 수성못길 123",
            phone="053-123-4567",
            latitude=35.8251,
            longitude=128.6212,
            image_url="https://via.placeholder.com/600x400?text=Suseongmot+Cafe",
        )
        # 장소에 태그 연결
        place1.tags.extend([tag1, tag3])

        place2 = Place(
            name="동성로 매운 갈비찜",
            category="RESTAURANT",
            region="중구",
            address="대구광역시 중구 동성로 45",
            phone="053-987-6543",
            latitude=35.8714,
            longitude=128.5960,
            image_url="https://via.placeholder.com/600x400?text=Spicy+Ribs",
        )
        place2.tags.extend([tag1, tag2])

        db.add_all([place1, place2])
        db.commit()

        print("✨ 더미 데이터 주입이 완료되었습니다!")

    except Exception as e:
        db.rollback()
        print(f"❌ 오류 발생: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
