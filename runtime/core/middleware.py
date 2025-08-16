"""
Custom middleware for the MCP Runtime Orchestrator.

This module provides middleware for tenant isolation, request logging,
error handling, and other cross-cutting concerns.
"""

import logging
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .exceptions import MCPRuntimeException, TenantIsolationError


logger = logging.getLogger(__name__)


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce tenant isolation.
    
    Extracts tenant_id from JWT token or request headers and adds it to
    request state for downstream use in database queries and RLS.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate correlation ID for request tracking
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Extract tenant_id from various sources
        tenant_id = None
        
        # 1. Try to get from Authorization header (JWT token)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # TODO: Decode JWT and extract tenant_id
            # For now, use a placeholder
            tenant_id = "default-tenant"
        
        # 2. Try to get from X-Tenant-ID header
        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID")
        
        # 3. For development, allow default tenant
        if not tenant_id:
            tenant_id = "default-tenant"
        
        # Validate tenant_id format
        if tenant_id and not self._is_valid_tenant_id(tenant_id):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "type": "invalid_tenant_id",
                        "message": "Invalid tenant ID format",
                        "correlation_id": correlation_id
                    }
                }
            )
        
        # Store in request state
        request.state.tenant_id = tenant_id
        
        # Add to logging context
        logger.info(
            "Request received",
            extra={
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "method": request.method,
                "url": str(request.url),
                "user_agent": request.headers.get("User-Agent")
            }
        )
        
        response = await call_next(request)
        
        # Add tenant and correlation headers to response
        response.headers["X-Correlation-ID"] = correlation_id
        if tenant_id:
            response.headers["X-Tenant-ID"] = tenant_id
        
        return response
    
    def _is_valid_tenant_id(self, tenant_id: str) -> bool:
        """Validate tenant ID format."""
        # Simple validation - adjust as needed
        return (
            isinstance(tenant_id, str) and
            len(tenant_id) > 0 and
            len(tenant_id) <= 100 and
            tenant_id.replace("-", "").replace("_", "").isalnum()
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log HTTP requests and responses.
    
    Logs request/response details with timing information and
    correlation IDs for observability.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get correlation ID from request state (set by TenantIsolationMiddleware)
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        tenant_id = getattr(request.state, "tenant_id", None)
        
        # Log request
        logger.info(
            "Request started",
            extra={
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent")
            }
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            "Request completed",
            extra={
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "process_time": round(process_time, 4),
                "response_size": response.headers.get("content-length", 0)
            }
        )
        
        # Add timing header
        response.headers["X-Process-Time"] = str(round(process_time, 4))
        
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle unhandled exceptions.
    
    Catches any exceptions that aren't handled by the application
    and returns a consistent error response.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except MCPRuntimeException:
            # Let MCPRuntimeExceptions bubble up to be handled by the global exception handler
            raise
        except Exception as exc:
            # Handle unexpected exceptions
            correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
            tenant_id = getattr(request.state, "tenant_id", None)
            
            logger.error(
                "Unhandled exception",
                exc_info=True,
                extra={
                    "correlation_id": correlation_id,
                    "tenant_id": tenant_id,
                    "method": request.method,
                    "url": str(request.url),
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)
                }
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_server_error",
                        "message": "An unexpected error occurred",
                        "correlation_id": correlation_id
                    }
                }
            )
