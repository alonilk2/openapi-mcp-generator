"""
Custom exceptions for the MCP Runtime Orchestrator.

This module defines application-specific exceptions with proper HTTP status codes
and structured error responses for better API error handling.
"""

from typing import Any, Dict, Optional


class MCPRuntimeException(Exception):
    """
    Base exception class for MCP Runtime Orchestrator.
    
    All custom exceptions should inherit from this class to ensure
    consistent error handling and logging.
    """
    
    def __init__(
        self,
        message: str,
        error_type: str = "runtime_error",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.details = details or {}


class ConnectorException(MCPRuntimeException):
    """Exception raised when connector operations fail."""
    
    def __init__(self, message: str, connector_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_type="connector_error", status_code=400, **kwargs)
        if connector_id:
            self.details["connector_id"] = connector_id


class ConnectorNotFoundError(ConnectorException):
    """Exception raised when a connector is not found."""
    
    def __init__(self, connector_id: str, **kwargs):
        super().__init__(
            f"Connector '{connector_id}' not found",
            connector_id=connector_id,
            error_type="connector_not_found",
            status_code=404,
            **kwargs
        )


class ConnectorValidationError(ConnectorException):
    """Exception raised when connector validation fails."""
    
    def __init__(self, message: str, validation_errors: Optional[list] = None, **kwargs):
        super().__init__(
            message,
            error_type="connector_validation_error",
            status_code=422,
            **kwargs
        )
        if validation_errors:
            self.details["validation_errors"] = validation_errors


class AuthenticationError(MCPRuntimeException):
    """Exception raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(
            message,
            error_type="authentication_error",
            status_code=401,
            **kwargs
        )


class AuthorizationError(MCPRuntimeException):
    """Exception raised when authorization fails."""
    
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(
            message,
            error_type="authorization_error",
            status_code=403,
            **kwargs
        )


class TenantIsolationError(MCPRuntimeException):
    """Exception raised when tenant isolation is violated."""
    
    def __init__(self, message: str = "Tenant isolation violation", tenant_id: Optional[str] = None, **kwargs):
        super().__init__(
            message,
            error_type="tenant_isolation_error",
            status_code=403,
            **kwargs
        )
        if tenant_id:
            self.details["tenant_id"] = tenant_id


class RateLimitExceededError(MCPRuntimeException):
    """Exception raised when rate limits are exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, **kwargs):
        super().__init__(
            message,
            error_type="rate_limit_exceeded",
            status_code=429,
            **kwargs
        )
        if retry_after:
            self.details["retry_after"] = retry_after


class ToolExecutionError(MCPRuntimeException):
    """Exception raised when tool execution fails."""
    
    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        connector_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message,
            error_type="tool_execution_error",
            status_code=500,
            **kwargs
        )
        if tool_name:
            self.details["tool_name"] = tool_name
        if connector_id:
            self.details["connector_id"] = connector_id


class ConfigurationError(MCPRuntimeException):
    """Exception raised when configuration is invalid."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            error_type="configuration_error",
            status_code=500,
            **kwargs
        )


class ExternalServiceError(MCPRuntimeException):
    """Exception raised when external service calls fail."""
    
    def __init__(
        self,
        message: str,
        service_name: Optional[str] = None,
        status_code: int = 502,
        **kwargs
    ):
        super().__init__(
            message,
            error_type="external_service_error",
            status_code=status_code,
            **kwargs
        )
        if service_name:
            self.details["service_name"] = service_name
