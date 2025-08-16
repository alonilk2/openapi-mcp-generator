"""
Tests for credential management API endpoints.

This module contains comprehensive tests for the credentials API endpoints
including storing, retrieving, listing, and deleting connector credentials.
"""

import pytest
import json
import tempfile
import shutil
import sys
import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Add the parent directory to the path for package imports
runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(runtime_dir)
sys.path.insert(0, parent_dir)

from runtime.main import create_app
from runtime.core.secret_factory import reset_secret_storage
from runtime.core.local_secrets import LocalSecretStorage


class TestCredentialsAPI:
    """Tests for the credentials API endpoints."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for secret storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def client(self, temp_storage_dir):
        """Create a test client with local secret storage."""
        # Reset global storage
        reset_secret_storage()
        
        # Mock the get_secret_storage function to use local storage
        async def mock_get_storage():
            return LocalSecretStorage(temp_storage_dir)
        
        with patch('runtime.api.credentials.get_secret_storage', mock_get_storage):
            app = create_app()
            with TestClient(app) as test_client:
                yield test_client

    def test_store_api_key_credentials(self, client):
        """Test storing API key credentials."""
        request_data = {
            "connector_name": "@github/api",
            "auth_type": "api_key",
            "credentials": {
                "value": "ghp_1234567890abcdef",
                "key_name": "authorization",
                "location": "header",
                "scheme": "Bearer"
            },
            "description": "GitHub personal access token",
            "tags": {"env": "test"},
            "expires_at": "2024-12-31T23:59:59Z"
        }
        
        response = client.post("/v1/credentials/", json=request_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["connector_name"] == "@github/api"
        assert data["auth_type"] == "api_key"
        assert data["description"] == "GitHub personal access token"
        assert data["tags"] == {"env": "test"}
        assert data["expires_at"] == "2024-12-31T23:59:59Z"
        assert data["has_credentials"] is True

    def test_store_oauth2_credentials(self, client):
        """Test storing OAuth2 client credentials."""
        request_data = {
            "connector_name": "@slack/api",
            "auth_type": "oauth2_client_credentials",
            "credentials": {
                "client_id": "slack_client_123",
                "client_secret": "slack_secret_456",
                "token_url": "https://slack.com/api/oauth.v2.access",
                "scopes": ["chat:write", "channels:read"]
            },
            "description": "Slack OAuth2 credentials"
        }
        
        response = client.post("/v1/credentials/", json=request_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["connector_name"] == "@slack/api"
        assert data["auth_type"] == "oauth2_client_credentials"
        assert data["description"] == "Slack OAuth2 credentials"
        assert data["has_credentials"] is True

    def test_store_credentials_invalid_auth_type(self, client):
        """Test storing credentials with invalid auth type."""
        request_data = {
            "connector_name": "test-connector",
            "auth_type": "invalid_type",
            "credentials": {"value": "test"}
        }
        
        response = client.post("/v1/credentials/", json=request_data)
        
        assert response.status_code == 422  # Validation error

    def test_store_credentials_missing_required_fields(self, client):
        """Test storing credentials with missing required fields."""
        request_data = {
            "connector_name": "test-connector",
            "auth_type": "api_key",
            "credentials": {}  # Missing 'value' field
        }
        
        response = client.post("/v1/credentials/", json=request_data)
        
        assert response.status_code == 422  # Validation error

    def test_list_credentials_empty(self, client):
        """Test listing credentials when none exist."""
        response = client.get("/v1/credentials/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["credentials"] == []
        assert data["total"] == 0

    def test_list_credentials_with_data(self, client):
        """Test listing credentials with stored data."""
        # Store some credentials first
        api_key_request = {
            "connector_name": "@github/api",
            "auth_type": "api_key",
            "credentials": {"value": "ghp_test"},
            "description": "GitHub token"
        }
        client.post("/v1/credentials/", json=api_key_request)
        
        oauth_request = {
            "connector_name": "@slack/api",
            "auth_type": "oauth2_client_credentials",
            "credentials": {
                "client_id": "slack_id",
                "client_secret": "slack_secret"
            },
            "description": "Slack OAuth2"
        }
        client.post("/v1/credentials/", json=oauth_request)
        
        # List all credentials
        response = client.get("/v1/credentials/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        
        credentials = data["credentials"]
        connector_names = [cred["connector_name"] for cred in credentials]
        assert "@github/api" in connector_names
        assert "@slack/api" in connector_names

    def test_list_credentials_filtered_by_connector(self, client):
        """Test listing credentials filtered by connector name."""
        # Store credentials for multiple connectors
        for connector in ["@github/api", "@slack/api"]:
            request_data = {
                "connector_name": connector,
                "auth_type": "api_key",
                "credentials": {"value": f"token_{connector}"}
            }
            client.post("/v1/credentials/", json=request_data)
        
        # Filter by connector name
        response = client.get("/v1/credentials/?connector_name=@github/api")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["credentials"][0]["connector_name"] == "@github/api"

    def test_list_credentials_filtered_by_auth_type(self, client):
        """Test listing credentials filtered by auth type."""
        # Store different types of credentials
        api_key_request = {
            "connector_name": "@github/api",
            "auth_type": "api_key",
            "credentials": {"value": "ghp_test"}
        }
        client.post("/v1/credentials/", json=api_key_request)
        
        oauth_request = {
            "connector_name": "@slack/api",
            "auth_type": "oauth2_client_credentials",
            "credentials": {
                "client_id": "slack_id",
                "client_secret": "slack_secret"
            }
        }
        client.post("/v1/credentials/", json=oauth_request)
        
        # Filter by auth type
        response = client.get("/v1/credentials/?auth_type=api_key")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["credentials"][0]["auth_type"] == "api_key"

    def test_get_credentials_api_key(self, client):
        """Test getting credentials for a specific connector with API key."""
        from urllib.parse import quote
        
        # Store API key credentials
        request_data = {
            "connector_name": "@github/api",
            "auth_type": "api_key",
            "credentials": {"value": "ghp_test"},
            "description": "GitHub token"
        }
        client.post("/v1/credentials/", json=request_data)
        
        # Get credentials (URL encode the connector name)
        encoded_name = quote("@github/api")
        response = client.get(f"/v1/credentials/{encoded_name}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["connector_name"] == "@github/api"
        assert data["auth_type"] == "api_key"
        assert data["description"] == "GitHub token"
        assert data["has_credentials"] is True

    def test_get_credentials_oauth2(self, client):
        """Test getting credentials for a specific connector with OAuth2."""
        from urllib.parse import quote
        
        # Store OAuth2 credentials
        request_data = {
            "connector_name": "@slack/api",
            "auth_type": "oauth2_client_credentials",
            "credentials": {
                "client_id": "slack_id",
                "client_secret": "slack_secret"
            },
            "description": "Slack OAuth2"
        }
        client.post("/v1/credentials/", json=request_data)
        
        # Get credentials (URL encode the connector name)
        encoded_name = quote("@slack/api")
        response = client.get(f"/v1/credentials/{encoded_name}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["connector_name"] == "@slack/api"
        assert data["auth_type"] == "oauth2_client_credentials"
        assert data["description"] == "Slack OAuth2"
        assert data["has_credentials"] is True

    def test_get_credentials_not_found(self, client):
        """Test getting credentials for a non-existent connector."""
        from urllib.parse import quote
        
        encoded_name = quote("nonexistent-connector")
        response = client.get(f"/v1/credentials/{encoded_name}")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_delete_credentials_api_key(self, client):
        """Test deleting API key credentials."""
        from urllib.parse import quote
        
        # Store credentials first
        request_data = {
            "connector_name": "@github/api",
            "auth_type": "api_key",
            "credentials": {"value": "ghp_test"}
        }
        client.post("/v1/credentials/", json=request_data)
        
        # Verify credentials exist
        encoded_name = quote("@github/api")
        response = client.get(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 200
        
        # Delete credentials
        response = client.delete(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 204
        
        # Verify credentials are gone
        response = client.get(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 404

    def test_delete_credentials_oauth2(self, client):
        """Test deleting OAuth2 credentials."""
        from urllib.parse import quote
        
        # Store credentials first
        request_data = {
            "connector_name": "@slack/api",
            "auth_type": "oauth2_client_credentials",
            "credentials": {
                "client_id": "slack_id",
                "client_secret": "slack_secret"
            }
        }
        client.post("/v1/credentials/", json=request_data)
        
        # Verify credentials exist
        encoded_name = quote("@slack/api")
        response = client.get(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 200
        
        # Delete credentials
        response = client.delete(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 204
        
        # Verify credentials are gone
        response = client.get(f"/v1/credentials/{encoded_name}")
        assert response.status_code == 404

    def test_delete_credentials_not_found(self, client):
        """Test deleting credentials for a non-existent connector."""
        from urllib.parse import quote
        
        encoded_name = quote("nonexistent-connector")
        response = client.delete(f"/v1/credentials/{encoded_name}")
        
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_credentials_api_error_handling(self, client):
        """Test error handling in credentials API."""
        # Mock storage error
        async def mock_get_storage_error():
            raise Exception("Storage unavailable")
        
        with patch('runtime.api.credentials.get_secret_storage', mock_get_storage_error):
            response = client.get("/v1/credentials/")
            
            assert response.status_code == 500
            data = response.json()
            assert "Unexpected error" in data["detail"]