"""Fraud Detector Hybrid — API Entry Point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import router as v1_router
from src.core.config import settings
from src.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize and tear down resources."""
    # Startup: verify DB connection
    try:
        async with engine.connect() as conn:
            await conn.run_sync(lambda _: None)
    except Exception as e:
        print(f"⚠️  Database connection failed: {e}")

    yield

    # Shutdown: dispose engine
    await engine.dispose()


app = FastAPI(
    title="Fraud Detector Hybrid",
    description="Sistema híbrido de detección de fraude con motor de reglas + LLM local",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount v1 router
app.include_router(v1_router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "fraud-detector"}


@app.get("/api/v1/status", tags=["status"])
async def api_status() -> dict[str, str]:
    """API status endpoint."""
    return {
        "version": "0.1.0",
        "environment": settings.environment,
    }
