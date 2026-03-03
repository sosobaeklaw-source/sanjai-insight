"""
sanjai-insight FastAPI Web Server
Exposes health check and operational endpoints for Railway deployment
"""

import os
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

from .api.health import get_healthz, get_health
from .api.status import get_status
from .api.cost import get_cost

app = FastAPI(
    title="sanjai-insight",
    version="2.0.0",
    description="산재AI 능동적 인사이트 시스템 - Operational API",
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "sanjai-insight",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/healthz")
async def healthz():
    """Simple liveness check for Railway"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    status_code, message = await get_healthz(db_path)

    if status_code == 200:
        return PlainTextResponse(content=message, status_code=200)
    else:
        return PlainTextResponse(content=message, status_code=503)


@app.get("/health")
async def health():
    """Detailed health status"""
    db_path = os.getenv("DB_PATH", "data/insight.db")
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")

    health_status = await get_health(db_path, telegram_token)
    return health_status.model_dump()


@app.get("/status")
async def status(correlation_id: str = None):
    """System status"""
    db_path = os.getenv("DB_PATH", "data/insight.db")

    if not correlation_id:
        return {
            "message": "Provide correlation_id query parameter",
            "example": "/status?correlation_id=xxx"
        }

    status_data = await get_status(db_path, correlation_id)
    if not status_data:
        return JSONResponse(
            status_code=404,
            content={"error": "Correlation ID not found"}
        )
    return status_data


@app.get("/cost")
async def cost(correlation_id: str = None):
    """Cost analysis"""
    db_path = os.getenv("DB_PATH", "data/insight.db")

    if not correlation_id:
        return {
            "message": "Provide correlation_id query parameter",
            "example": "/cost?correlation_id=xxx"
        }

    cost_data = await get_cost(db_path, correlation_id)
    if not cost_data:
        return JSONResponse(
            status_code=404,
            content={"error": "Correlation ID not found"}
        )
    return cost_data


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
