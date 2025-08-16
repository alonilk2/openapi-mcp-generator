"""
Core module for the MCP Runtime Orchestrator.

This module contains the foundational components including configuration,
logging, middleware, exceptions, and built-in tools.
"""

from .config import Settings, get_settings
from .exceptions import (
    MCPRuntimeException,
    ConnectorException,
    ConnectorNotFoundError,
    ConnectorValidationError,
    AuthenticationError,
    AuthorizationError,
    TenantIsolationError,
    RateLimitExceededError,
    ToolExecutionError,
    ConfigurationError,
    ExternalServiceError,
)
from .logging import setup_logging, get_logger, LoggerMixin
from .middleware import (
    TenantIsolationMiddleware,
    RequestLoggingMiddleware,
    ErrorHandlingMiddleware,
)
from .builtin_tools import (
    BuiltinToolHandler,
    BuiltinTool,
    ToolParameter,
    ToolExecutionResult,
    builtin_tool_handler,
)

__all__ = [
    # Configuration
    "Settings",
    "get_settings",
    # Exceptions
    "MCPRuntimeException",
    "ConnectorException",
    "ConnectorNotFoundError",
    "ConnectorValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "TenantIsolationError",
    "RateLimitExceededError",
    "ToolExecutionError",
    "ConfigurationError",
    "ExternalServiceError",
    # Logging
    "setup_logging",
    "get_logger",
    "LoggerMixin",
    # Middleware
    "TenantIsolationMiddleware",
    "RequestLoggingMiddleware",
    "ErrorHandlingMiddleware",
    # Built-in Tools
    "BuiltinToolHandler",
    "BuiltinTool",
    "ToolParameter",
    "ToolExecutionResult",
    "builtin_tool_handler",
]
