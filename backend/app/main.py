from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_routes import router as admin_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.observability import RequestObservabilityMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )
    app.add_middleware(RequestObservabilityMiddleware)
    app.include_router(router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    return app


app = create_app()
