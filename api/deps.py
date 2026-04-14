import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.config import settings
from db.mysql import get_db
from models.user import User

# OAuth2PasswordBearer: 프론트엔드가 HTTP 헤더에 담아 보낸 토큰('Bearer xxxx...')을
# 자동으로 추출해 주고, Swagger UI 우측 상단에 'Authorize' 자물쇠 버튼을 만들어줌
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login/swagger", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    API 요청 헤더의 JWT를 검증하고, 현재 로그인한 유저의 DB 객체를 반환하는 함수
    """
    # 토큰을 안 들고 온 경우
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다. (Authorization 헤더 누락)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # 토큰 위변조 및 만료 검사
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")

        # 내용물이 이상하거나, Refresh Token을 들고 Access API에 접근하려는 경우 차단
        if user_id is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다."
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다. 다시 로그인해주세요.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="토큰 해독에 실패했습니다."
        )

    # 토큰은 정상인데, DB에 유저가 없는 경우
    user = db.query(User).filter(User.user_id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="존재하지 않는 유저입니다."
        )

    # 모든 검문을 통과하면 안전한 User 객체를 반환
    return user
