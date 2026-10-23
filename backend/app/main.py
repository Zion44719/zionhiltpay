"""
ZionhiltPay — FastAPI application entrypoint.
Powered by Zionhilt.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.config import settings
from app.core.limiter import limiter
from app.core.database import engine, Base
from app.core.db_guards import install_db_guards
from app.core.migrations import upgrade_schema, seed_platform_accounts
from app.core.crypto import validate_encryption_key
from app.api import auth, wallet, devices, admin, banks, tier, profile, loans, partners, agent

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("zionhiltpay")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ZionhiltPay backend starting up (env=%s)", settings.APP_ENV)
    # Dev convenience: ensure tables exist. In production, use Alembic
    # migrations (see db/schema.sql + alembic/) instead of relying on this.
    validate_encryption_key()
    if settings.APP_ENV == "production":
        if not settings.DATA_ENCRYPTION_KEY:
            raise RuntimeError("DATA_ENCRYPTION_KEY must be set in production (government ID numbers are encrypted with it).")
        if settings.JWT_SECRET_KEY.startswith("CHANGE_ME"):
            raise RuntimeError("JWT_SECRET_KEY is still the placeholder value; set a strong secret in production.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await upgrade_schema(conn)     # add new columns/indexes to older databases, backfill account numbers
        await install_db_guards(conn)  # append-only ledger/audit + updated_at triggers
    async with engine.begin() as conn:
        await seed_platform_accounts(conn)  # separate transaction: new enum values must be committed first
    logger.info("Database schema verified/created; integrity guards installed.")
    yield
    logger.info("ZionhiltPay backend shutting down.")
    await engine.dispose()


app = FastAPI(
    title="ZionhiltPay API",
    description="Digital wallet with transaction rewards and device insurance. Powered by Zionhilt.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Adds baseline security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Our team has been notified."},
    )


app.include_router(auth.router)
app.include_router(wallet.router)
app.include_router(devices.router)
app.include_router(admin.router)
app.include_router(banks.router)
app.include_router(tier.router)
app.include_router(profile.router)
app.include_router(loans.router)
app.include_router(partners.public)
app.include_router(partners.admin)
app.include_router(agent.router)


@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@app.get("/", tags=["health"])
async def root():
    return {
        "message": "ZionhiltPay API is running. Powered by Zionhilt.",
        "docs": "/docs",
        "health": "/api/health",
    }
