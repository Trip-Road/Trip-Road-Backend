from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from core.config import settings


def create_access_token(subject: Any, expires_delta: timedelta = None) -> str:
    """
    API 접근용 Access Token을 생성합니다. (기본 유효기간 1일)
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # 페이로드 구성: 'sub'는 토큰의 주인을 의미 (여기서는 user_id)
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}

    # 서버의 SECRET_KEY를 이용해 토큰을 암호화하여 반환
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(subject: Any) -> str:
    """
    Access Token 갱신용 Refresh Token을 생성 (기본 유효기간 14일)
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
