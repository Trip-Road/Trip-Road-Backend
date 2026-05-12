from fastapi import APIRouter

from api.v1 import (
    auth_router,
    event_router,
    favorite_router,
    place_router,
    tag_router,
    user_router,
    weather_router,
)

api_router = APIRouter()

api_router.include_router(place_router.router, prefix="/places", tags=["Places"])
api_router.include_router(auth_router.router, prefix="/auth", tags=["Auth"])
api_router.include_router(user_router.router, prefix="/users", tags=["Users"])
api_router.include_router(tag_router.router, prefix="/tags", tags=["Tags"])
api_router.include_router(favorite_router.router, prefix="/favorites", tags=["Favorites"])
api_router.include_router(weather_router.router, prefix="/weather", tags=["Weather"])
api_router.include_router(event_router.router, prefix="/events", tags=["Events"])
