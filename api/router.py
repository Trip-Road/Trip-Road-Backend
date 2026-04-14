from fastapi import APIRouter

from api.v1 import auth_router, place_router, user_router

api_router = APIRouter()

api_router.include_router(place_router.router, prefix="/places", tags=["Places"])

api_router.include_router(auth_router.router, prefix="/auth", tags=["Auth"])

api_router.include_router(user_router.router, prefix="/users", tags=["Users"])
