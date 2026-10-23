import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.errors import error_response, install_error_handlers
from app.core.security import validate_security_config
from app.db.base import engine
from app.routers import (
    admin,
    applications,
    assurance,
    auth,
    digilocker,
    documents,
    institutions,
    issuers,
    review,
    issuer,
    upload,
    validation,
    verifier,
    verify,
    zkp,
)
from app.services.object_store import get_object_store

logger = logging.getLogger(__name__)
validate_security_config()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials="*" not in origins,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "If-Match", "Idempotency-Key", "X-Request-ID"],
)

install_error_handlers(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:20]}"
    request.state.request_id = request_id
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    duration_ms = int((time.monotonic() - started) * 1000)
    if response.status_code >= 400:
        logger.info(
            "request_failed request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_REQUEST_BYTES:
                return error_response(
                    request, 413, "REQUEST_TOO_LARGE", "The request exceeds the configured size limit."
                )
        except ValueError:
            return error_response(request, 400, "VALIDATION_FAILED", "Invalid Content-Length header.")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith(settings.API_V1_STR):
        response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Mount legacy routers
app.include_router(upload.router, prefix=settings.API_V1_STR)
app.include_router(digilocker.router, prefix=settings.API_V1_STR)
app.include_router(issuer.router, prefix=settings.API_V1_STR)
app.include_router(verify.router, prefix=settings.API_V1_STR)
app.include_router(verifier.router, prefix=settings.API_V1_STR)

# Phase 3 routers
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(institutions.router, prefix=settings.API_V1_STR)
app.include_router(applications.router, prefix=settings.API_V1_STR)
app.include_router(documents.router, prefix=settings.API_V1_STR)
app.include_router(admin.router, prefix=settings.API_V1_STR)
app.include_router(validation.router, prefix=settings.API_V1_STR)
app.include_router(issuers.router, prefix=settings.API_V1_STR)
app.include_router(assurance.router, prefix=settings.API_V1_STR)
app.include_router(review.router, prefix=settings.API_V1_STR)
app.include_router(zkp.router, prefix=f"{settings.API_V1_STR}/zkp")


@app.get("/")
async def root():
    return {
        "title": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "ONLINE",
        "docs_url": "/docs",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "tesseract_path": settings.TESSERACT_CMD,
        "storage_dir": str(settings.UPLOAD_DIR),
        "digilocker_configured": bool(
            settings.DIGILOCKER_CLIENT_ID and settings.DIGILOCKER_CLIENT_SECRET
        ),
    }


@app.get("/ready")
def readiness_check():
    try:
        with engine.connect():
            pass
        get_object_store()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready", "database": "ok", "storage": "ok"}
