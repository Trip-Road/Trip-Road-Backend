from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.mysql import get_db
from models.tag import Tag
from schemas.response import TagResponse

router = APIRouter()


@router.get("/", response_model=Dict[str, List[TagResponse]])
def get_all_tags(db: Session = Depends(get_db)):
    """
    DB에 저장된 모든 태그를 카테고리별로 그룹화하여 프론트엔드에 전달
    """
    tags = db.query(Tag).all()

    grouped_tags = {"COMMON": [], "RESTAURANT": [], "CAFE": [], "ATTRACTION": []}

    for tag in tags:
        category_key = str(tag.tag_category)

        if category_key not in grouped_tags:
            grouped_tags[category_key] = []

        grouped_tags[category_key].append(TagResponse(tag_id=tag.tag_id, tag_name=tag.tag_name))

    return grouped_tags
