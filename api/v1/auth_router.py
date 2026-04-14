from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from core.config import settings
from core.security import create_access_token, create_refresh_token
from db.mysql import get_db
from models.user import User
from schemas.request import GoogleLoginRequest
from schemas.response import LoginResponse, TokenResponse, UserResponse

router = APIRouter()


@router.post("/login/google", response_model=LoginResponse)
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    """
    프론트엔드에서 받은 구글 id_token을 검증하고,
    신규/기존 유저를 구분하여 자체 JWT를 발급
    """
    # 구글 토큰 검증
    try:
        # 이 함수가 구글 서버와 통신하여 토큰이 진짜인지, 만료되진 않았는지 검사
        payload = id_token.verify_oauth2_token(
            request.id_token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 구글 토큰입니다.",
        )

    # 페이로드에서 안전하게 정보 추출
    google_id = payload.get("sub")
    email = payload.get("email")
    google_name = payload.get("name")
    google_picture = payload.get("picture")

    # 우리 DB에서 유저 조회
    user = db.query(User).filter(User.google_id == google_id).first()

    if not user:
        # 신규 유저 가입 처리
        user = User(
            google_id=google_id,
            email=email,
            nickname=google_name,
            profile_image_url=google_picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # 기존 유저 로그인 처리
        pass

    # 우리 서비스 전용 JWT 발급
    access_token = create_access_token(subject=user.user_id)
    refresh_token = create_refresh_token(subject=user.user_id)

    # 발급된 Refresh Token을 DB에 저장하여 추후 검증에 사용
    user.refresh_token = refresh_token
    db.commit()

    # 설계한 DTO 규격에 맞춰 응답 포장
    return LoginResponse(
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
        user=UserResponse(
            user_id=user.user_id,
            email=user.email,
            nickname=user.nickname,
            profile_image_url=user.profile_image_url,
            # 온보딩 완료 여부는 모델의 필드나, 선호 태그 존재 여부로 판단
            # (가정: user.is_onboarded 라는 컬럼이나 property가 존재)
            is_onboarded=getattr(user, "is_onboarded", False),
        ),
    )
