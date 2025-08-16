"""
Core configuration module for the MCP Runtime Orchestrator.

This module handles all configuration settings using Pydantic Settings
with support for environment variables and Azure-specific configuration.
"""

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables with the
    MCP_RUNTIME_ prefix (e.g., MCP_RUNTIME_DEBUG=true).
    """
    
    # Application metadata
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(default="development", description="Environment name (development, staging, production)")
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    
    # Server configuration
    HOST: str = Field(default="0.0.0.0", description="Host to bind the server to")
    PORT: int = Field(default=8000, description="Port to bind the server to")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    
    # Security
    ALLOWED_HOSTS: List[str] = Field(default=["*"], description="Allowed host headers")
    CORS_ORIGINS: List[str] = Field(default=["*"], description="Allowed CORS origins")
    
    # JWT Configuration
    JWT_SECRET_KEY: Optional[str] = Field(default=None, description="JWT secret key")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_EXPIRATION_HOURS: int = Field(default=24, description="JWT token expiration in hours")
    
    # Database Configuration
    DATABASE_URL: Optional[str] = Field(default=None, description="PostgreSQL database URL")
    DATABASE_POOL_SIZE: int = Field(default=10, description="Database connection pool size")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, description="Database max overflow connections")
    
    # Redis Configuration
    REDIS_URL: Optional[str] = Field(default=None, description="Redis connection URL")
    REDIS_POOL_SIZE: int = Field(default=10, description="Redis connection pool size")
    
    # Azure Configuration
    AZURE_TENANT_ID: Optional[str] = Field(default=None, description="Azure AD tenant ID")
    AZURE_CLIENT_ID: Optional[str] = Field(default=None, description="Azure AD client ID")
    AZURE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Azure AD client secret")
    AZURE_KEY_VAULT_URL: Optional[str] = Field(default=None, description="Azure Key Vault URL")
    AZURE_STORAGE_ACCOUNT: Optional[str] = Field(default=None, description="Azure Storage account name")
    AZURE_STORAGE_CONTAINER: str = Field(default="connectors", description="Azure Storage container name")
    
    # MCP Runtime Configuration
    MAX_CONCURRENT_CONNECTORS: int = Field(default=100, description="Maximum concurrent connector instances")
    CONNECTOR_TIMEOUT_SECONDS: int = Field(default=30, description="Default connector timeout in seconds")
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=1000, description="Default rate limit per minute")
    
    # Observability
    ENABLE_METRICS: bool = Field(default=True, description="Enable Prometheus metrics")
    ENABLE_TRACING: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = Field(default=None, description="OTLP exporter endpoint")
    
    # Development settings
    HOT_RELOAD: bool = Field(default=False, description="Enable hot reload for connectors in development")
    
    model_config = {
        "env_prefix": "MCP_RUNTIME_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT.lower() == "development"
    
    def get_database_url(self) -> str:
        """Get the database URL with fallback to default."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        
        # Default development database
        return "postgresql://postgres:postgres@localhost:5432/mcp_runtime"
    
    def get_redis_url(self) -> str:
        """Get the Redis URL with fallback to default."""
        if self.REDIS_URL:
            return self.REDIS_URL
        
        # Default development Redis
        return "redis://localhost:6379/0"


@lru_cache()
def get_settings() -> Settings:
    """
    Get application settings with caching.
    
    The @lru_cache decorator ensures that this function returns the same
    Settings instance for the lifetime of the application.
    """
    return Settings()
