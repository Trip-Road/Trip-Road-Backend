from fastapi import FastAPI

import models.history_and_event  # noqa: F401
import models.place  # noqa: F401
import models.tag  # noqa: F401
import models.user  # noqa: F401
from api.router import api_router
from core.config import settings
from db.mysql import engine
from models.base import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "message": "Trip Road API is successfully running!"}
