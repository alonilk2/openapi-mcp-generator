"""
Health check endpoints for the MCP Runtime Orchestrator.

This module provides health check endpoints for monitoring and
load balancer health checks.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.config import Settings, get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    status: str
    version: str
    environment: str
    services: dict[str, str]


@router.get("/", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Basic health check endpoint.
    
    Returns the service status, version, and environment.
    Used by load balancers for basic health monitoring.
    """
    return HealthResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT
    )


@router.get("/live", response_model=HealthResponse)
async def liveness_check(settings: Settings = Depends(get_settings)):
    """
    Kubernetes liveness probe endpoint.
    
    Returns whether the service is running and responsive.
    """
    return HealthResponse(
        status="alive",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(settings: Settings = Depends(get_settings)):
    """
    Kubernetes readiness probe endpoint.
    
    Returns whether the service is ready to accept traffic.
    Checks connectivity to dependent services.
    """
    # TODO: Add actual service dependency checks
    # - Database connectivity
    # - Redis connectivity
    # - Azure Key Vault connectivity
    
    services = {
        "database": "healthy",  # TODO: Check actual database connection
        "redis": "healthy",     # TODO: Check actual Redis connection
        "keyvault": "healthy",  # TODO: Check actual Key Vault connection
    }
    
    return ReadinessResponse(
        status="ready",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        services=services
    )
