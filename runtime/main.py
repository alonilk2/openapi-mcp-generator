"""
MCP Runtime Orchestrator - FastAPI Application

This is the main entry point for the Runtime Orchestrator service that acts as
an MCP gateway, loading connectors and handling tool calls with built-in auth,
retries, rate limiting, and observability.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from api import health, mcp, projects, runtime
from core.config import get_settings
from core.logging import setup_logging
from core.middleware import (
    TenantIsolationMiddleware,
    RequestLoggingMiddleware,
    ErrorHandlingMiddleware
)
from core.exceptions import MCPRuntimeException
from core.registry import get_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager for startup and shutdown events.
    """
    settings = get_settings()
    logger = logging.getLogger(__name__)
    
    # Startup
    logger.info("Starting MCP Runtime Orchestrator", extra={
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG
    })
    
    # Initialize registry and load sample connectors for Phase 0-1
    registry = get_registry()
    await load_sample_connectors(registry, logger)
    
    yield
    
    # Shutdown
    logger.info("Shutting down MCP Runtime Orchestrator")


async def load_sample_connectors(registry, logger):
    """Load sample connectors for Phase 0-1 demonstration."""
    from pathlib import Path
    
    try:
        logger.info("Starting sample connector loading")
        
        # Create default project registry
        project_id = "default"
        tenant_id = "default-tenant"
        project_registry = registry.create_project_registry(project_id, tenant_id)
        logger.info(f"Project registry created: {project_id}")
        
        # Load sample connectors from samples directory
        samples_dir = Path(__file__).parent / "samples"
        logger.info(f"Samples directory: {samples_dir} (exists: {samples_dir.exists()})")
        
        if samples_dir.exists():
            yaml_files = list(samples_dir.glob("*.yaml"))
            logger.info(f"Found {len(yaml_files)} YAML files")
            
            for yaml_file in yaml_files:
                try:
                    logger.info(f"Loading connector from: {yaml_file}")
                    connector = registry.load_connector_from_file(
                        project_id, 
                        yaml_file
                    )
                    registry.install_connector(project_id, connector)
                    
                    logger.info(
                        "Sample connector loaded successfully",
                        extra={
                            "connector_name": connector.name,
                            "connector_version": connector.version,
                            "tool_count": len(connector.tools),
                            "file_path": str(yaml_file)
                        }
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to load sample connector",
                        extra={
                            "file_path": str(yaml_file),
                            "error": str(e)
                        }
                    )
        else:
            logger.warning(f"Samples directory not found: {samples_dir}")
        
        # Log registry stats
        stats = registry.get_registry_stats()
        logger.info(
            "Connector registry initialized",
            extra={
                "total_projects": stats["total_projects"],
                "total_connectors": stats["total_connectors"],
                "total_tools": stats["total_tools"],
                "hot_reload_enabled": stats["hot_reload_enabled"]
            }
        )
        
    except Exception as e:
        logger.error(
            "Failed to initialize connector registry",
            exc_info=True,
            extra={"error": str(e)}
        )


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    """
    settings = get_settings()
    
    # Setup logging before creating the app
    setup_logging(settings.LOG_LEVEL, settings.DEBUG)
    
    app = FastAPI(
        title="MCP Runtime Orchestrator",
        description="Runtime service for the MCP + 'npm of APIs' platform that loads connectors and handles tool calls",
        version=settings.VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )
    
    # Security middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Custom middleware (order matters - added in reverse order of execution)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TenantIsolationMiddleware)
    
    # Include routers
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(mcp.router, prefix="/v1/mcp", tags=["mcp"])
    app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
    app.include_router(runtime.router, prefix="/v1/runtime", tags=["runtime"])
    
    # Import and include credentials router
    from api import credentials
    app.include_router(credentials.router, tags=["credentials"])
    
    # Global exception handler
    @app.exception_handler(MCPRuntimeException)
    async def mcp_exception_handler(request: Request, exc: MCPRuntimeException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": exc.error_type,
                    "message": exc.message,
                    "details": exc.details,
                    "correlation_id": getattr(request.state, "correlation_id", None)
                }
            }
        )
    
    return app


# Create the FastAPI app instance
app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True,
    )
