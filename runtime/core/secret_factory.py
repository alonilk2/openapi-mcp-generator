"""
Secret storage factory and management utilities.

This module provides factory functions and utilities for creating and managing
secret storage backends based on configuration.
"""

import os
from typing import Optional
from enum import Enum

from .config import get_settings
from .secrets import SecretStorageInterface
from .local_secrets import create_local_secret_storage
from .azure_secrets import create_azure_keyvault_storage


class SecretStorageType(Enum):
    """Supported secret storage backend types."""
    LOCAL = "local"
    AZURE_KEYVAULT = "azure_keyvault"


class SecretStorageFactory:
    """Factory for creating secret storage instances."""
    
    @staticmethod
    def create_storage(
        storage_type: Optional[SecretStorageType] = None,
        **kwargs
    ) -> SecretStorageInterface:
        """
        Create a secret storage instance based on configuration.
        
        Args:
            storage_type: Type of storage to create (auto-detected if None)
            **kwargs: Additional arguments for storage creation
            
        Returns:
            Configured SecretStorageInterface instance
            
        Raises:
            ValueError: If storage type is invalid or configuration is missing
        """
        settings = get_settings()
        
        if storage_type is None:
            storage_type = SecretStorageFactory._detect_storage_type()
        
        if storage_type == SecretStorageType.LOCAL:
            return SecretStorageFactory._create_local_storage(**kwargs)
        elif storage_type == SecretStorageType.AZURE_KEYVAULT:
            return SecretStorageFactory._create_azure_storage(**kwargs)
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")
    
    @staticmethod
    def _detect_storage_type() -> SecretStorageType:
        """
        Auto-detect the appropriate storage type based on configuration.
        
        Returns:
            SecretStorageType based on available configuration
        """
        settings = get_settings()
        
        # If Azure Key Vault URL is configured and we're not in development, use Azure
        if (settings.AZURE_KEY_VAULT_URL and 
            not settings.is_development() and 
            settings.AZURE_KEY_VAULT_URL.startswith("https://")):
            return SecretStorageType.AZURE_KEYVAULT
        
        # Default to local storage for development or when Azure is not configured
        return SecretStorageType.LOCAL
    
    @staticmethod
    def _create_local_storage(**kwargs) -> SecretStorageInterface:
        """Create local file-based secret storage."""
        storage_dir = kwargs.get("storage_dir")
        if not storage_dir:
            # Default to runtime directory + secrets
            storage_dir = os.path.join(os.getcwd(), ".secrets")
        
        encryption_key = kwargs.get("encryption_key")
        if not encryption_key:
            # Try to get from environment variable
            encryption_key = os.getenv("MCP_SECRET_ENCRYPTION_KEY")
        
        return create_local_secret_storage(storage_dir, encryption_key)
    
    @staticmethod
    def _create_azure_storage(**kwargs) -> SecretStorageInterface:
        """Create Azure Key Vault secret storage."""
        settings = get_settings()
        
        vault_url = kwargs.get("vault_url", settings.AZURE_KEY_VAULT_URL)
        if not vault_url:
            raise ValueError("Azure Key Vault URL is required but not configured")
        
        return create_azure_keyvault_storage(vault_url)


# Global storage instance (lazy-loaded)
_storage_instance: Optional[SecretStorageInterface] = None


async def get_secret_storage() -> SecretStorageInterface:
    """
    Get the global secret storage instance.
    
    This function provides a singleton-like interface for accessing the secret
    storage throughout the application. The storage type is determined by
    configuration.
    
    Returns:
        SecretStorageInterface instance
    """
    global _storage_instance
    
    if _storage_instance is None:
        _storage_instance = SecretStorageFactory.create_storage()
    
    return _storage_instance


async def close_secret_storage() -> None:
    """
    Close the global secret storage instance.
    
    This should be called during application shutdown to properly clean up
    resources.
    """
    global _storage_instance
    
    if _storage_instance is not None:
        await _storage_instance.close()
        _storage_instance = None


def reset_secret_storage() -> None:
    """
    Reset the global secret storage instance.
    
    This is useful for testing when you need to switch storage backends or
    clear the cached instance.
    """
    global _storage_instance
    _storage_instance = None