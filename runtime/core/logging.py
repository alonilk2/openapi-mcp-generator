"""
Logging configuration for the MCP Runtime Orchestrator.

This module sets up structured logging with JSON formatting for production
and human-readable formatting for development, including correlation IDs
and tenant context.
"""

import logging
import logging.config
import sys
from typing import Any, Dict

import uvicorn


def setup_logging(log_level: str = "INFO", debug: bool = False) -> None:
    """
    Configure application logging.
    
    Args:
        log_level: The log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        debug: Whether to use debug formatting (human-readable vs JSON)
    """
    
    # Configure the root logger
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "detailed": {
                "format": (
                    "%(asctime)s - %(name)s - %(levelname)s - "
                    "[%(filename)s:%(lineno)d] - %(message)s"
                )
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": (
                    "%(asctime)s %(name)s %(levelname)s %(filename)s "
                    "%(lineno)d %(message)s"
                )
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "detailed" if debug else "default",
                "level": log_level
            }
        },
        "loggers": {
            "": {  # Root logger
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn.access": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "uvicorn.error": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "fastapi": {
                "level": log_level,
                "handlers": ["console"],
                "propagate": False
            },
            "httpx": {
                "level": "WARNING",
                "handlers": ["console"],
                "propagate": False
            }
        }
    }
    
    logging.config.dictConfig(logging_config)
    
    # Set up uvicorn logging
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    
    # Create a custom formatter for structured logging
    class StructuredFormatter(logging.Formatter):
        """Custom formatter that adds structured data to log records."""
        
        def format(self, record: logging.LogRecord) -> str:
            # Add default structured data
            if not hasattr(record, 'correlation_id'):
                record.correlation_id = None
            if not hasattr(record, 'tenant_id'):
                record.tenant_id = None
            if not hasattr(record, 'user_id'):
                record.user_id = None
            
            return super().format(record)
    
    # Apply structured formatter to console handler if in debug mode
    if debug:
        console_handler = logging.getLogger().handlers[0]
        console_handler.setFormatter(StructuredFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - "
            "[%(filename)s:%(lineno)d] - "
            "[correlation_id=%(correlation_id)s] [tenant_id=%(tenant_id)s] - "
            "%(message)s"
        ))


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: The logger name (typically __name__)
        
    Returns:
        A configured logger instance
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class that provides a logger instance to any class.
    
    Usage:
        class MyClass(LoggerMixin):
            def some_method(self):
                self.logger.info("Hello, world!")
    """
    
    @property
    def logger(self) -> logging.Logger:
        """Get a logger instance for this class."""
        return logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
