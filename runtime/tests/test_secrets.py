"""
Tests for secret storage implementations.

This module contains comprehensive tests for all secret storage backends
including local file storage and Azure Key Vault integration.
"""

import pytest
import tempfile
import shutil
import os
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Add the parent directory to the path for package imports
runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(runtime_dir)
sys.path.insert(0, parent_dir)

from runtime.core.secrets import (
    SecretType,
    SecretMetadata,
    SecretValue,
    SecretStorageError,
    SecretNotFoundError,
    generate_secret_name
)
from runtime.core.local_secrets import LocalSecretStorage
from runtime.core.secret_factory import SecretStorageFactory, SecretStorageType


class TestSecretMetadata:
    """Tests for SecretMetadata class."""

    def test_secret_metadata_creation(self):
        """Test creating SecretMetadata with all fields."""
        metadata = SecretMetadata(
            name="test-secret",
            secret_type=SecretType.API_KEY,
            connector_name="@github/api",
            description="GitHub API token",
            tags={"env": "prod", "team": "platform"},
            expires_at="2024-12-31T23:59:59Z"
        )
        
        assert metadata.name == "test-secret"
        assert metadata.secret_type == SecretType.API_KEY
        assert metadata.connector_name == "@github/api"
        assert metadata.description == "GitHub API token"
        assert metadata.tags == {"env": "prod", "team": "platform"}
        assert metadata.expires_at == "2024-12-31T23:59:59Z"

    def test_secret_metadata_minimal(self):
        """Test creating SecretMetadata with minimal fields."""
        metadata = SecretMetadata(
            name="simple-secret",
            secret_type=SecretType.OAUTH2_CLIENT_ID,
            connector_name="slack"
        )
        
        assert metadata.name == "simple-secret"
        assert metadata.secret_type == SecretType.OAUTH2_CLIENT_ID
        assert metadata.connector_name == "slack"
        assert metadata.description is None
        assert metadata.tags == {}
        assert metadata.expires_at is None


class TestSecretValue:
    """Tests for SecretValue class."""

    def test_secret_value_creation(self):
        """Test creating SecretValue."""
        metadata = SecretMetadata(
            name="test-key",
            secret_type=SecretType.API_KEY,
            connector_name="test"
        )
        secret_value = SecretValue("secret123", metadata)
        
        assert secret_value.value == "secret123"
        assert secret_value.metadata == metadata

    def test_secret_value_str_redaction(self):
        """Test that SecretValue redacts the actual value in string representation."""
        metadata = SecretMetadata(
            name="test-key",
            secret_type=SecretType.API_KEY,
            connector_name="test"
        )
        secret_value = SecretValue("secret123", metadata)
        
        str_repr = str(secret_value)
        assert "secret123" not in str_repr
        assert "test-key" in str_repr
        assert "api_key" in str_repr

    def test_secret_value_repr_redaction(self):
        """Test that SecretValue redacts the actual value in repr."""
        metadata = SecretMetadata(
            name="test-key",
            secret_type=SecretType.API_KEY,
            connector_name="test"
        )
        secret_value = SecretValue("secret123", metadata)
        
        repr_str = repr(secret_value)
        assert "secret123" not in repr_str
        assert "test-key" in repr_str
        assert "api_key" in repr_str


class TestGenerateSecretName:
    """Tests for generate_secret_name utility function."""

    def test_generate_secret_name_basic(self):
        """Test basic secret name generation."""
        name = generate_secret_name("@github/api", SecretType.API_KEY)
        assert name == "github-api-api_key"

    def test_generate_secret_name_with_suffix(self):
        """Test secret name generation with suffix."""
        name = generate_secret_name("slack", SecretType.OAUTH2_CLIENT_ID, "prod")
        assert name == "slack-oauth2_client_id-prod"

    def test_generate_secret_name_special_chars(self):
        """Test secret name generation with special characters."""
        name = generate_secret_name("@org/my-connector", SecretType.API_KEY)
        assert name == "org-my-connector-api_key"
        assert "@" not in name
        assert "/" not in name


@pytest.mark.asyncio
class TestLocalSecretStorage:
    """Tests for LocalSecretStorage implementation."""

    @pytest.fixture
    async def temp_storage(self):
        """Create a temporary storage directory for testing."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalSecretStorage(temp_dir)
        yield storage
        await storage.close()
        shutil.rmtree(temp_dir)

    @pytest.fixture
    async def storage_with_secrets(self, temp_storage):
        """Create storage with some test secrets."""
        await temp_storage.store_secret(
            name="github-token",
            value="ghp_1234567890abcdef",
            secret_type=SecretType.API_KEY,
            connector_name="@github/api",
            description="GitHub personal access token",
            tags={"env": "test"}
        )
        
        await temp_storage.store_secret(
            name="slack-client-id",
            value="client123",
            secret_type=SecretType.OAUTH2_CLIENT_ID,
            connector_name="@slack/api",
            description="Slack OAuth client ID"
        )
        
        return temp_storage

    async def test_store_and_get_secret(self, temp_storage):
        """Test storing and retrieving a secret."""
        await temp_storage.store_secret(
            name="test-secret",
            value="super-secret-value",
            secret_type=SecretType.API_KEY,
            connector_name="test-connector",
            description="Test secret",
            tags={"env": "test", "version": "1.0"},
            expires_at="2024-12-31T23:59:59Z"
        )
        
        secret_value = await temp_storage.get_secret("test-secret")
        
        assert secret_value.value == "super-secret-value"
        assert secret_value.metadata.name == "test-secret"
        assert secret_value.metadata.secret_type == SecretType.API_KEY
        assert secret_value.metadata.connector_name == "test-connector"
        assert secret_value.metadata.description == "Test secret"
        assert secret_value.metadata.tags == {"env": "test", "version": "1.0"}
        assert secret_value.metadata.expires_at == "2024-12-31T23:59:59Z"

    async def test_get_nonexistent_secret(self, temp_storage):
        """Test retrieving a non-existent secret."""
        with pytest.raises(SecretNotFoundError):
            await temp_storage.get_secret("nonexistent-secret")

    async def test_secret_exists(self, storage_with_secrets):
        """Test checking if secrets exist."""
        assert await storage_with_secrets.secret_exists("github-token") is True
        assert await storage_with_secrets.secret_exists("nonexistent") is False

    async def test_delete_secret(self, storage_with_secrets):
        """Test deleting a secret."""
        assert await storage_with_secrets.secret_exists("github-token") is True
        
        await storage_with_secrets.delete_secret("github-token")
        
        assert await storage_with_secrets.secret_exists("github-token") is False
        
        with pytest.raises(SecretNotFoundError):
            await storage_with_secrets.get_secret("github-token")

    async def test_delete_nonexistent_secret(self, temp_storage):
        """Test deleting a non-existent secret."""
        with pytest.raises(SecretNotFoundError):
            await temp_storage.delete_secret("nonexistent")

    async def test_list_all_secrets(self, storage_with_secrets):
        """Test listing all secrets."""
        secrets = await storage_with_secrets.list_secrets()
        
        assert len(secrets) == 2
        
        names = [s.name for s in secrets]
        assert "github-token" in names
        assert "slack-client-id" in names

    async def test_list_secrets_by_connector(self, storage_with_secrets):
        """Test listing secrets filtered by connector."""
        secrets = await storage_with_secrets.list_secrets(connector_name="@github/api")
        
        assert len(secrets) == 1
        assert secrets[0].name == "github-token"
        assert secrets[0].connector_name == "@github/api"

    async def test_list_secrets_by_type(self, storage_with_secrets):
        """Test listing secrets filtered by type."""
        secrets = await storage_with_secrets.list_secrets(secret_type=SecretType.OAUTH2_CLIENT_ID)
        
        assert len(secrets) == 1
        assert secrets[0].name == "slack-client-id"
        assert secrets[0].secret_type == SecretType.OAUTH2_CLIENT_ID

    async def test_update_secret_metadata(self, storage_with_secrets):
        """Test updating secret metadata."""
        await storage_with_secrets.update_secret_metadata(
            name="github-token",
            description="Updated description",
            tags={"env": "prod", "updated": "true"},
            expires_at="2025-01-01T00:00:00Z"
        )
        
        secret_value = await storage_with_secrets.get_secret("github-token")
        
        assert secret_value.metadata.description == "Updated description"
        assert secret_value.metadata.tags == {"env": "prod", "updated": "true"}
        assert secret_value.metadata.expires_at == "2025-01-01T00:00:00Z"

    async def test_update_nonexistent_secret_metadata(self, temp_storage):
        """Test updating metadata for non-existent secret."""
        with pytest.raises(SecretNotFoundError):
            await temp_storage.update_secret_metadata("nonexistent", description="test")

    async def test_clear_all_secrets(self, storage_with_secrets):
        """Test clearing all secrets."""
        # Verify secrets exist
        secrets = await storage_with_secrets.list_secrets()
        assert len(secrets) == 2
        
        # Clear all secrets
        storage_with_secrets.clear_all_secrets()
        
        # Verify all secrets are gone
        secrets = await storage_with_secrets.list_secrets()
        assert len(secrets) == 0
        
        assert await storage_with_secrets.secret_exists("github-token") is False
        assert await storage_with_secrets.secret_exists("slack-client-id") is False


class TestSecretStorageFactory:
    """Tests for SecretStorageFactory."""

    def test_create_local_storage(self):
        """Test creating local storage via factory."""
        storage = SecretStorageFactory.create_storage(
            storage_type=SecretStorageType.LOCAL,
            storage_dir="/tmp/test-secrets"
        )
        
        assert isinstance(storage, LocalSecretStorage)

    def test_create_storage_invalid_type(self):
        """Test creating storage with invalid type."""
        with pytest.raises(ValueError, match="Unsupported storage type"):
            SecretStorageFactory.create_storage(storage_type="invalid")

    @patch('runtime.core.secret_factory.get_settings')
    def test_detect_storage_type_development(self, mock_get_settings):
        """Test auto-detection defaults to local in development."""
        mock_settings = Mock()
        mock_settings.is_development.return_value = True
        mock_settings.AZURE_KEY_VAULT_URL = None
        mock_get_settings.return_value = mock_settings
        
        storage_type = SecretStorageFactory._detect_storage_type()
        assert storage_type == SecretStorageType.LOCAL

    @patch('runtime.core.secret_factory.get_settings')
    def test_detect_storage_type_azure(self, mock_get_settings):
        """Test auto-detection chooses Azure when configured and not in dev."""
        mock_settings = Mock()
        mock_settings.is_development.return_value = False
        mock_settings.AZURE_KEY_VAULT_URL = "https://test.vault.azure.net/"
        mock_get_settings.return_value = mock_settings
        
        storage_type = SecretStorageFactory._detect_storage_type()
        assert storage_type == SecretStorageType.AZURE_KEYVAULT