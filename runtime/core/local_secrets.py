"""
Local file-based secret storage implementation for development.

This module provides a development-friendly secret storage backend using
encrypted local files. Suitable for development and testing environments.
"""

import asyncio
import json
import os
import base64
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .secrets import (
    SecretStorageInterface,
    SecretType,
    SecretMetadata,
    SecretValue,
    SecretStorageError,
    SecretNotFoundError
)


class LocalSecretStorage(SecretStorageInterface):
    """
    Local file-based secret storage with encryption.
    
    This implementation stores secrets in encrypted files on the local filesystem.
    It's designed for development and testing environments where Azure Key Vault
    is not available or desired.
    """

    def __init__(self, storage_dir: str, encryption_key: Optional[str] = None):
        """
        Initialize local secret storage.
        
        Args:
            storage_dir: Directory to store encrypted secret files
            encryption_key: Optional encryption key (will generate one if not provided)
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize encryption
        if encryption_key:
            self.encryption_key = encryption_key.encode()
        else:
            self.encryption_key = self._get_or_create_key()
        
        self.fernet = self._create_fernet(self.encryption_key)
        
        # Metadata file path
        self.metadata_file = self.storage_dir / "secrets_metadata.json"
        self.metadata = self._load_metadata()

    def _get_or_create_key(self) -> bytes:
        """Get existing encryption key or create a new one."""
        key_file = self.storage_dir / ".encryption_key"
        
        if key_file.exists():
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate a new key
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions on the key file
            os.chmod(key_file, 0o600)
            return key

    def _create_fernet(self, key: bytes) -> Fernet:
        """Create Fernet encryption instance."""
        return Fernet(key)

    def _load_metadata(self) -> Dict[str, Dict]:
        """Load metadata from the metadata file."""
        if not self.metadata_file.exists():
            return {}
        
        try:
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_metadata(self) -> None:
        """Save metadata to the metadata file."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            # Set restrictive permissions on metadata file
            os.chmod(self.metadata_file, 0o600)
        except IOError as e:
            raise SecretStorageError(f"Failed to save metadata: {e}")

    def _get_secret_file_path(self, name: str) -> Path:
        """Get the file path for a secret."""
        # Use base64 encoding to handle special characters in names
        safe_name = base64.urlsafe_b64encode(name.encode()).decode().rstrip('=')
        return self.storage_dir / f"{safe_name}.secret"

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
        """Store a secret in encrypted local file."""
        try:
            # Encrypt the secret value
            encrypted_value = self.fernet.encrypt(value.encode())
            
            # Store encrypted value to file
            secret_file = self._get_secret_file_path(name)
            with open(secret_file, 'wb') as f:
                f.write(encrypted_value)
            
            # Set restrictive permissions
            os.chmod(secret_file, 0o600)
            
            # Store metadata
            self.metadata[name] = {
                "secret_type": secret_type.value,
                "connector_name": connector_name,
                "description": description,
                "tags": tags or {},
                "expires_at": expires_at,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            self._save_metadata()
            
        except Exception as e:
            raise SecretStorageError(f"Failed to store secret locally: {e}")

    async def get_secret(self, name: str) -> SecretValue:
        """Retrieve a secret from encrypted local file."""
        try:
            if name not in self.metadata:
                raise SecretNotFoundError(f"Secret '{name}' not found")
            
            # Check if secret file exists
            secret_file = self._get_secret_file_path(name)
            if not secret_file.exists():
                raise SecretNotFoundError(f"Secret file for '{name}' not found")
            
            # Read and decrypt the secret value
            with open(secret_file, 'rb') as f:
                encrypted_value = f.read()
            
            try:
                decrypted_value = self.fernet.decrypt(encrypted_value).decode()
            except Exception as e:
                raise SecretStorageError(f"Failed to decrypt secret '{name}': {e}")
            
            # Build metadata
            meta_data = self.metadata[name]
            try:
                secret_type = SecretType(meta_data["secret_type"])
            except (ValueError, KeyError):
                secret_type = SecretType.API_KEY
            
            metadata = SecretMetadata(
                name=name,
                secret_type=secret_type,
                connector_name=meta_data.get("connector_name", "unknown"),
                description=meta_data.get("description"),
                tags=meta_data.get("tags", {}),
                expires_at=meta_data.get("expires_at")
            )
            
            return SecretValue(value=decrypted_value, metadata=metadata)
            
        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretStorageError(f"Failed to retrieve secret locally: {e}")

    async def delete_secret(self, name: str) -> None:
        """Delete a secret from local storage."""
        try:
            if name not in self.metadata:
                raise SecretNotFoundError(f"Secret '{name}' not found")
            
            # Delete the secret file
            secret_file = self._get_secret_file_path(name)
            if secret_file.exists():
                secret_file.unlink()
            
            # Remove from metadata
            del self.metadata[name]
            self._save_metadata()
            
        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretStorageError(f"Failed to delete secret locally: {e}")

    async def list_secrets(
        self,
        connector_name: Optional[str] = None,
        secret_type: Optional[SecretType] = None
    ) -> List[SecretMetadata]:
        """List secrets with optional filtering."""
        try:
            secrets = []
            
            for name, meta_data in self.metadata.items():
                # Apply filters
                if connector_name and meta_data.get("connector_name") != connector_name:
                    continue
                
                if secret_type and meta_data.get("secret_type") != secret_type.value:
                    continue
                
                try:
                    parsed_secret_type = SecretType(meta_data.get("secret_type", "api_key"))
                except ValueError:
                    parsed_secret_type = SecretType.API_KEY
                
                metadata = SecretMetadata(
                    name=name,
                    secret_type=parsed_secret_type,
                    connector_name=meta_data.get("connector_name", "unknown"),
                    description=meta_data.get("description"),
                    tags=meta_data.get("tags", {}),
                    expires_at=meta_data.get("expires_at")
                )
                secrets.append(metadata)
            
            return secrets
            
        except Exception as e:
            raise SecretStorageError(f"Failed to list secrets locally: {e}")

    async def secret_exists(self, name: str) -> bool:
        """Check if a secret exists in local storage."""
        return name in self.metadata and self._get_secret_file_path(name).exists()

    async def update_secret_metadata(
        self,
        name: str,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        expires_at: Optional[str] = None
    ) -> None:
        """Update metadata for an existing secret."""
        try:
            if name not in self.metadata:
                raise SecretNotFoundError(f"Secret '{name}' not found")
            
            # Update metadata
            if description is not None:
                self.metadata[name]["description"] = description
            
            if tags is not None:
                self.metadata[name]["tags"] = tags
            
            if expires_at is not None:
                self.metadata[name]["expires_at"] = expires_at
            
            self.metadata[name]["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            self._save_metadata()
            
        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretStorageError(f"Failed to update secret metadata locally: {e}")

    async def close(self) -> None:
        """Close the local storage (no cleanup needed for file-based storage)."""
        pass

    def clear_all_secrets(self) -> None:
        """
        Clear all secrets (useful for testing).
        
        WARNING: This will permanently delete all stored secrets!
        """
        try:
            # Delete all secret files
            for name in self.metadata.keys():
                secret_file = self._get_secret_file_path(name)
                if secret_file.exists():
                    secret_file.unlink()
            
            # Clear metadata
            self.metadata.clear()
            self._save_metadata()
            
        except Exception as e:
            raise SecretStorageError(f"Failed to clear all secrets: {e}")


def create_local_secret_storage(storage_dir: str, encryption_key: Optional[str] = None) -> LocalSecretStorage:
    """
    Factory function to create a local secret storage instance.
    
    Args:
        storage_dir: Directory to store encrypted secret files
        encryption_key: Optional encryption key
        
    Returns:
        Configured LocalSecretStorage instance
    """
    return LocalSecretStorage(storage_dir, encryption_key)