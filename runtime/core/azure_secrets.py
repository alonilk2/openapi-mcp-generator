"""
Azure Key Vault implementation of the secret storage interface.

This module provides a production-ready secret storage backend using Azure Key Vault
for secure credential management in cloud environments.
"""

import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime

from azure.keyvault.secrets.aio import SecretClient
from azure.identity.aio import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

from .secrets import (
    SecretStorageInterface,
    SecretType,
    SecretMetadata,
    SecretValue,
    SecretStorageError,
    SecretNotFoundError
)


class AzureKeyVaultStorage(SecretStorageInterface):
    """
    Azure Key Vault implementation of secret storage.
    
    This implementation stores secrets in Azure Key Vault with proper metadata
    management using secret tags and properties.
    """

    def __init__(self, vault_url: str, credential: Optional[DefaultAzureCredential] = None):
        """
        Initialize Azure Key Vault storage.
        
        Args:
            vault_url: URL of the Azure Key Vault (e.g., https://myvault.vault.azure.net/)
            credential: Optional Azure credential instance (defaults to DefaultAzureCredential)
        """
        self.vault_url = vault_url
        self.credential = credential or DefaultAzureCredential()
        self.client = SecretClient(vault_url=vault_url, credential=self.credential)
        
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
        """Store a secret in Azure Key Vault."""
        try:
            # Prepare tags for Key Vault
            vault_tags = {
                "secret_type": secret_type.value,
                "connector_name": connector_name,
                "managed_by": "mcp_runtime"
            }
            
            if tags:
                # Filter out reserved tag names and ensure string values
                for key, val in tags.items():
                    if key not in vault_tags:
                        vault_tags[key] = str(val)
            
            # Convert expires_at to datetime if provided
            expires_on = None
            if expires_at:
                try:
                    expires_on = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError as e:
                    raise SecretStorageError(f"Invalid expires_at format: {e}")
            
            # Store the secret
            await self.client.set_secret(
                name=name,
                value=value,
                content_type="text/plain",
                tags=vault_tags,
                expires_on=expires_on
            )
            
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to store secret in Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error storing secret: {e}")

    async def get_secret(self, name: str) -> SecretValue:
        """Retrieve a secret from Azure Key Vault."""
        try:
            secret = await self.client.get_secret(name)
            
            # Extract metadata from tags
            tags = secret.properties.tags or {}
            secret_type_str = tags.get("secret_type", "api_key")
            connector_name = tags.get("connector_name", "unknown")
            
            try:
                secret_type = SecretType(secret_type_str)
            except ValueError:
                secret_type = SecretType.API_KEY
            
            # Build metadata
            metadata = SecretMetadata(
                name=name,
                secret_type=secret_type,
                connector_name=connector_name,
                description=None,  # Azure Key Vault doesn't have a separate description field
                tags={k: v for k, v in tags.items() if k not in ["secret_type", "connector_name", "managed_by"]},
                expires_at=secret.properties.expires_on.isoformat() if secret.properties.expires_on else None
            )
            
            return SecretValue(value=secret.value, metadata=metadata)
            
        except ResourceNotFoundError:
            raise SecretNotFoundError(f"Secret '{name}' not found in Azure Key Vault")
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to retrieve secret from Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error retrieving secret: {e}")

    async def delete_secret(self, name: str) -> None:
        """Delete a secret from Azure Key Vault."""
        try:
            # Check if secret exists first
            if not await self.secret_exists(name):
                raise SecretNotFoundError(f"Secret '{name}' not found")
            
            # Begin deletion (this starts the deletion process)
            await self.client.begin_delete_secret(name)
            
        except ResourceNotFoundError:
            raise SecretNotFoundError(f"Secret '{name}' not found in Azure Key Vault")
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to delete secret from Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error deleting secret: {e}")

    async def list_secrets(
        self,
        connector_name: Optional[str] = None,
        secret_type: Optional[SecretType] = None
    ) -> List[SecretMetadata]:
        """List secrets from Azure Key Vault with optional filtering."""
        try:
            secrets = []
            
            # List all secret properties (not values)
            async for secret_properties in self.client.list_properties_of_secrets():
                # Skip deleted secrets
                if secret_properties.enabled is False:
                    continue
                
                tags = secret_properties.tags or {}
                secret_connector = tags.get("connector_name")
                secret_type_str = tags.get("secret_type", "api_key")
                
                # Apply filters
                if connector_name and secret_connector != connector_name:
                    continue
                
                if secret_type and secret_type_str != secret_type.value:
                    continue
                
                # Only include secrets managed by MCP
                if tags.get("managed_by") != "mcp_runtime":
                    continue
                
                try:
                    parsed_secret_type = SecretType(secret_type_str)
                except ValueError:
                    parsed_secret_type = SecretType.API_KEY
                
                metadata = SecretMetadata(
                    name=secret_properties.name,
                    secret_type=parsed_secret_type,
                    connector_name=secret_connector or "unknown",
                    description=None,
                    tags={k: v for k, v in tags.items() if k not in ["secret_type", "connector_name", "managed_by"]},
                    expires_at=secret_properties.expires_on.isoformat() if secret_properties.expires_on else None
                )
                secrets.append(metadata)
            
            return secrets
            
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to list secrets from Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error listing secrets: {e}")

    async def secret_exists(self, name: str) -> bool:
        """Check if a secret exists in Azure Key Vault."""
        try:
            await self.client.get_secret(name)
            return True
        except ResourceNotFoundError:
            return False
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to check secret existence in Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error checking secret existence: {e}")

    async def update_secret_metadata(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        expires_at: Optional[str] = None
    ) -> None:
        """Update metadata for an existing secret in Azure Key Vault."""
        try:
            # Get the current secret to preserve existing tags
            secret = await self.client.get_secret(name)
            current_tags = secret.properties.tags or {}
            
            # Update tags while preserving system tags
            updated_tags = current_tags.copy()
            if tags:
                for key, val in tags.items():
                    if key not in ["secret_type", "connector_name", "managed_by"]:
                        updated_tags[key] = str(val)
            
            # Convert expires_at to datetime if provided
            expires_on = None
            if expires_at:
                try:
                    expires_on = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError as e:
                    raise SecretStorageError(f"Invalid expires_at format: {e}")
            
            # Update secret properties
            await self.client.update_secret_properties(
                name=name,
                tags=updated_tags,
                expires_on=expires_on
            )
            
        except ResourceNotFoundError:
            raise SecretNotFoundError(f"Secret '{name}' not found in Azure Key Vault")
        except HttpResponseError as e:
            raise SecretStorageError(f"Failed to update secret metadata in Azure Key Vault: {e}")
        except Exception as e:
            raise SecretStorageError(f"Unexpected error updating secret metadata: {e}")

    async def close(self) -> None:
        """Close the Azure Key Vault client and credential."""
        try:
            await self.client.close()
            await self.credential.close()
        except Exception as e:
            # Log the error but don't raise it during cleanup
            print(f"Warning: Error closing Azure Key Vault client: {e}")


def create_azure_keyvault_storage(vault_url: str) -> AzureKeyVaultStorage:
    """
    Factory function to create an Azure Key Vault storage instance.
    
    Args:
        vault_url: URL of the Azure Key Vault
        
    Returns:
        Configured AzureKeyVaultStorage instance
    """
    return AzureKeyVaultStorage(vault_url)