"""
Main FastAPI Application - Multi-Agent RAG Orchestrator v4.2 API

Provides REST API for:
- Budget management
- LLMOps analytics
- Provider management
- RAG search
- MCP operations
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..utils.shutdown import ShutdownPhase, shutdown_manager
from .budget import router as budget_router
from .health import router as health_router

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Lifespan context manager
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Startup and shutdown logic with graceful shutdown support (TASK-045).
    """
    # Startup
    logger.info("=" * 70)
    logger.info("  Starting Multi-Agent RAG Orchestrator API v4.2")
    logger.info("=" * 70)
    logger.info("Budget API: /api/v1/budget")
    logger.info("Health API: /health")
    logger.info("Documentation: /docs")

    # Setup signal handlers for graceful shutdown
    await shutdown_manager.setup_signal_handlers()

    # Register shutdown hooks
    # Example hooks - in production, register actual resource cleanup
    shutdown_manager.register(
        name="Stop background tasks",
        phase=ShutdownPhase.STOP_BACKGROUND,
        callback=lambda: logger.info("Background tasks stopped"),
        critical=False,
    )

    shutdown_manager.register(
        name="Close database connections",
        phase=ShutdownPhase.CLOSE_CONNECTIONS,
        callback=lambda: logger.info("Database connections closed"),
        critical=True,
    )

    shutdown_manager.register(
        name="Final cleanup",
        phase=ShutdownPhase.CLEANUP,
        callback=lambda: logger.info("Cleanup complete"),
        critical=False,
    )

    logger.info("Graceful shutdown hooks registered")
    logger.info("API ready to serve requests")
    logger.info("=" * 70)

    yield

    # Shutdown - execute graceful shutdown
    logger.info("Initiating shutdown sequence...")
    await shutdown_manager.shutdown()
    logger.info("API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Multi-Agent RAG Orchestrator",
    description=(
        "Production-grade RAG orchestration with multi-tier LLMs, "
        "cost tracking, and privacy mode"
    ),
    version="4.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    logger.info(
        "%s %s status=%s duration=%.3fs",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )

    return response


# Include routers
app.include_router(budget_router)
app.include_router(health_router)


# Root endpoint
@app.get("/")
async def root():
    """API root with version and health info"""
    return {
        "name": "Multi-Agent RAG Orchestrator API",
        "version": "4.2.0",
        "status": "operational",
        "endpoints": {
            "documentation": "/docs",
            "budget": "/api/v1/budget",
            "health": "/health",
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "startup": "/health/startup",
        },
    }


# Health check
@app.get("/health")
async def health_check():
    """Overall health check"""
    return {
        "status": "healthy",
        "version": "4.2.0",
        "components": {"api": "operational", "budget": "operational"},
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, _exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"Endpoint {request.url.path} not found",
            "documentation": "/docs",
        },
    )


@app.exception_handler(500)
async def internal_error_handler(_request: Request, exc):
    """Custom 500 handler"""
    logger.error("Internal error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
