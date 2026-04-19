from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from api.deps import get_current_user
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
    try:
        payload = id_token.verify_oauth2_token(
            request.id_token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 구글 토큰입니다.",
        )

    google_id = payload.get("sub")
    google_name = payload.get("name")
    google_picture = payload.get("picture")

    user = db.query(User).filter(User.google_id == google_id).first()

    if not user:
        # 신규 유저 가입 처리
        user = User(
            google_id=google_id,
            nickname=google_name,
            profile_image=google_picture,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # 기존 유저 로그인 처리
        pass

    access_token = create_access_token(subject=user.user_id)
    refresh_token = create_refresh_token(subject=user.user_id)

    user.refresh_token = refresh_token
    db.commit()

    return LoginResponse(
        tokens=TokenResponse(access_token=access_token, refresh_token=refresh_token),
        user=UserResponse(
            user_id=user.user_id,
            nickname=user.nickname,
            profile_image=user.profile_image,
            is_onboarded=getattr(user, "is_onboarded", False),
        ),
    )


@router.post("/login/swagger")
def login_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    [개발용] Swagger UI 우측 상단 자물쇠 버튼을 작동시키기 위한 API
    username 칸에 유저 ID(숫자)를 입력하면 강제로 해당 유저의 토큰을 발급
    """
    user_id = int(form_data.username)
    user = db.query(User).filter(User.user_id == user_id).first()

    if not user:
        user = User(
            google_id=f"test_google_{user_id}",
            nickname=f"테스터{user_id}",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token(subject=user.user_id)

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    유저의 Refresh Token을 무효화
    """
    current_user.refresh_token = None
    db.commit()

    return {"message": "성공적으로 로그아웃 되었습니다."}
