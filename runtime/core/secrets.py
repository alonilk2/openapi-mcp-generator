"""
Secret storage abstraction for the MCP Runtime.

This module provides a unified interface for managing secrets across different
storage backends, including Azure Key Vault for production and encrypted local
storage for development.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from enum import Enum
import asyncio


class SecretType(Enum):
    """Types of secrets that can be stored."""
    API_KEY = "api_key"
    OAUTH2_CLIENT_ID = "oauth2_client_id"
    OAUTH2_CLIENT_SECRET = "oauth2_client_secret"
    OAUTH2_REFRESH_TOKEN = "oauth2_refresh_token"
    OAUTH2_ACCESS_TOKEN = "oauth2_access_token"


class SecretMetadata:
    """Metadata for a stored secret."""
    
    def __init__(
        self,
        name: str,
        secret_type: SecretType,
        connector_name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        expires_at: Optional[str] = None
    ):
        self.name = name
        self.secret_type = secret_type
        self.connector_name = connector_name
        self.description = description
        self.tags = tags or {}
        self.expires_at = expires_at


class SecretValue:
    """Container for a secret value with metadata."""
    
    def __init__(self, value: str, metadata: SecretMetadata):
        self.value = value
        self.metadata = metadata

    def __str__(self) -> str:
        """Redact the actual value when converting to string."""
        return f"SecretValue(name={self.metadata.name}, type={self.metadata.secret_type.value})"

    def __repr__(self) -> str:
        """Redact the actual value in repr."""
        return self.__str__()


class SecretStorageError(Exception):
    """Base exception for secret storage operations."""
    pass


class SecretNotFoundError(SecretStorageError):
    """Raised when a requested secret is not found."""
    pass


class SecretStorageInterface(ABC):
    """
    Abstract interface for secret storage backends.
    
    This interface defines the contract that all secret storage implementations
    must follow, ensuring consistent behavior across different backends.
    """

    @abstractmethod
    async def store_secret(
        self,
        name: str,
        value: str,
        secret_type: SecretType,
        connector_name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        expires_at: Optional[str] = None
    ) -> None:
        """
        Store a secret with metadata.
        
        Args:
            name: Unique identifier for the secret
            value: The secret value to store
            secret_type: Type of secret being stored
            connector_name: Name of the connector this secret belongs to
            description: Optional description of the secret
            tags: Optional key-value tags for the secret
            expires_at: Optional expiration timestamp (ISO 8601 format)
            
        Raises:
            SecretStorageError: If storage operation fails
        """
        pass

    @abstractmethod
    async def get_secret(self, name: str) -> SecretValue:
        """
        Retrieve a secret by name.
        
        Args:
            name: Unique identifier for the secret
            
        Returns:
            SecretValue containing the secret value and metadata
            
        Raises:
            SecretNotFoundError: If secret is not found
            SecretStorageError: If retrieval operation fails
        """
        pass

    @abstractmethod
    async def delete_secret(self, name: str) -> None:
        """
        Delete a secret by name.
        
        Args:
            name: Unique identifier for the secret
            
        Raises:
            SecretNotFoundError: If secret is not found
            SecretStorageError: If deletion operation fails
        """
        pass

    @abstractmethod
    async def list_secrets(
        self,
        connector_name: Optional[str] = None,
        secret_type: Optional[SecretType] = None
    ) -> List[SecretMetadata]:
        """
        List secrets with optional filtering.
        
        Args:
            connector_name: Filter by connector name
            secret_type: Filter by secret type
            
        Returns:
            List of SecretMetadata for matching secrets
            
        Raises:
            SecretStorageError: If listing operation fails
        """
        pass

    @abstractmethod
    async def secret_exists(self, name: str) -> bool:
        """
        Check if a secret exists.
        
        Args:
            name: Unique identifier for the secret
            
        Returns:
            True if secret exists, False otherwise
            
        Raises:
            SecretStorageError: If check operation fails
        """
        pass

    @abstractmethod
    async def update_secret_metadata(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        expires_at: Optional[str] = None
    ) -> None:
        """
        Update metadata for an existing secret.
        
        Args:
            name: Unique identifier for the secret
            description: New description for the secret
            tags: New tags for the secret
            expires_at: New expiration timestamp
            
        Raises:
            SecretNotFoundError: If secret is not found
            SecretStorageError: If update operation fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close the storage backend and clean up resources.
        
        This method should be called when the storage backend is no longer needed.
        """
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def generate_secret_name(connector_name: str, secret_type: SecretType, suffix: Optional[str] = None) -> str:
    """
    Generate a standardized secret name.
    
    Args:
        connector_name: Name of the connector
        secret_type: Type of secret
        suffix: Optional suffix for the secret name
        
    Returns:
        Standardized secret name
    """
    base_name = f"{connector_name}-{secret_type.value}"
    if suffix:
        base_name += f"-{suffix}"
    return base_name.replace("@", "").replace("/", "-").lower()