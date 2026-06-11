"""Fraud Detector Hybrid — API Entry Point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings

app = FastAPI(
    title="Fraud Detector Hybrid",
    description="Sistema híbrido de detección de fraude con motor de reglas + LLM local",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
