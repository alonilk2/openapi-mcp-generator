"""
Tests for credential resolution and authenticated HTTP client.

This module contains tests for the credential resolution service and
authenticated HTTP client used for executing connector tools.
"""

import pytest
import tempfile
import shutil
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

# Add the parent directory to the path for package imports
runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(runtime_dir)
sys.path.insert(0, parent_dir)

from runtime.core.credential_resolver import (
    CredentialResolver,
    CredentialResolutionError,
    ResolvedCredentials,
    get_credential_resolver,
    reset_credential_resolver
)
from runtime.core.authenticated_client import (
    AuthenticatedHttpClient,
    ToolExecutionClient,
    get_tool_execution_client,
    reset_tool_execution_client
)
from runtime.core.local_secrets import LocalSecretStorage
from runtime.core.secrets import SecretType, generate_secret_name
from runtime.models.manifest import ConnectorTool, ApiKeyAuth, OAuth2ClientCredentialsAuth, NoAuth


@pytest.mark.asyncio
class TestCredentialResolver:
    """Tests for the CredentialResolver class."""

    @pytest.fixture
    async def temp_storage(self):
        """Create a temporary storage with test credentials."""
        temp_dir = tempfile.mkdtemp()
        storage = LocalSecretStorage(temp_dir)
        
        # Store API key credentials
        await storage.store_secret(
            name=generate_secret_name("@github/api", SecretType.API_KEY),
            value="ghp_test_token",
            secret_type=SecretType.API_KEY,
            connector_name="@github/api",
            description="GitHub API token",
            tags={
                "key_name": "authorization",
                "location": "header",
                "scheme": "Bearer"
            }
        )
        
        # Store OAuth2 credentials
        await storage.store_secret(
            name=generate_secret_name("@slack/api", SecretType.OAUTH2_CLIENT_ID),
            value="slack_client_123",
            secret_type=SecretType.OAUTH2_CLIENT_ID,
            connector_name="@slack/api",
            description="Slack client ID",
            tags={
                "token_url": "https://slack.com/api/oauth.v2.access",
                "scopes": "chat:write,channels:read"
            }
        )
        
        await storage.store_secret(
            name=generate_secret_name("@slack/api", SecretType.OAUTH2_CLIENT_SECRET),
            value="slack_secret_456",
            secret_type=SecretType.OAUTH2_CLIENT_SECRET,
            connector_name="@slack/api",
            description="Slack client secret",
            tags={
                "token_url": "https://slack.com/api/oauth.v2.access",
                "scopes": "chat:write,channels:read"
            }
        )
        
        yield storage
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def resolver(self):
        """Create a credential resolver instance."""
        reset_credential_resolver()
        return CredentialResolver()

    async def test_resolve_no_auth_credentials(self, resolver):
        """Test resolving credentials for a tool with no authentication."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint",
            auth=NoAuth()
        )
        
        credentials = await resolver.resolve_credentials(tool, "test-connector")
        
        assert credentials.auth_type == "none"
        assert not credentials.has_credentials()
        assert credentials.headers == {}
        assert credentials.query_params == {}
        assert credentials.cookies == {}

    async def test_resolve_api_key_credentials(self, resolver, temp_storage):
        """Test resolving API key credentials."""
        tool = ConnectorTool(
            name="get_user",
            description="Get GitHub user",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="github.users.get",
            auth=ApiKeyAuth(
                key_name="authorization",
                location="header",
                scheme="Bearer"
            )
        )
        
        with patch('runtime.core.credential_resolver.get_secret_storage', return_value=temp_storage):
            credentials = await resolver.resolve_credentials(tool, "@github/api")
        
        assert credentials.auth_type == "api_key"
        assert credentials.has_credentials()
        assert "authorization" in credentials.headers
        assert credentials.headers["authorization"] == "Bearer ghp_test_token"
        assert credentials.query_params == {}
        assert credentials.cookies == {}

    async def test_resolve_api_key_query_location(self, resolver, temp_storage):
        """Test resolving API key credentials for query parameter location."""
        # Update the stored secret to use query location
        secret_name = generate_secret_name("@github/api", SecretType.API_KEY)
        await temp_storage.update_secret_metadata(
            name=secret_name,
            tags={
                "key_name": "api_key",
                "location": "query",
                "scheme": ""
            }
        )
        
        tool = ConnectorTool(
            name="get_user",
            description="Get GitHub user",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="github.users.get",
            auth=ApiKeyAuth(
                key_name="api_key",
                location="query"
            )
        )
        
        with patch('runtime.core.credential_resolver.get_secret_storage', return_value=temp_storage):
            credentials = await resolver.resolve_credentials(tool, "@github/api")
        
        assert credentials.auth_type == "api_key"
        assert credentials.has_credentials()
        assert credentials.headers == {}
        assert "api_key" in credentials.query_params
        assert credentials.query_params["api_key"] == "ghp_test_token"
        assert credentials.cookies == {}

    async def test_resolve_oauth2_credentials(self, resolver, temp_storage):
        """Test resolving OAuth2 credentials."""
        tool = ConnectorTool(
            name="send_message",
            description="Send Slack message",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="slack.chat.postMessage",
            auth=OAuth2ClientCredentialsAuth(
                token_url="https://slack.com/api/oauth.v2.access",
                scopes=["chat:write", "channels:read"]
            )
        )
        
        # Mock the OAuth2 token request
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "xoxb-test-token-123"}
        
        with patch('runtime.core.credential_resolver.get_secret_storage', return_value=temp_storage), \
             patch('httpx.AsyncClient') as mock_client:
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            credentials = await resolver.resolve_credentials(tool, "@slack/api")
        
        assert credentials.auth_type == "oauth2_client_credentials"
        assert credentials.has_credentials()
        assert "Authorization" in credentials.headers
        assert credentials.headers["Authorization"] == "Bearer xoxb-test-token-123"
        assert credentials.oauth_token == "xoxb-test-token-123"

    async def test_resolve_credentials_missing_secret(self, resolver):
        """Test resolving credentials when secret is missing."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint",
            auth=ApiKeyAuth(
                key_name="api_key",
                location="header"
            )
        )
        
        # Use empty storage
        temp_dir = tempfile.mkdtemp()
        empty_storage = LocalSecretStorage(temp_dir)
        
        try:
            with patch('runtime.core.credential_resolver.get_secret_storage', return_value=empty_storage):
                with pytest.raises(CredentialResolutionError, match="No API key found"):
                    await resolver.resolve_credentials(tool, "nonexistent-connector")
        finally:
            shutil.rmtree(temp_dir)

    async def test_validate_credentials_success(self, resolver, temp_storage):
        """Test validating credentials when they exist."""
        tool = ConnectorTool(
            name="get_user",
            description="Get GitHub user",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="github.users.get",
            auth=ApiKeyAuth(
                key_name="authorization",
                location="header",
                scheme="Bearer"
            )
        )
        
        with patch('runtime.core.credential_resolver.get_secret_storage', return_value=temp_storage):
            is_valid = await resolver.validate_credentials(tool, "@github/api")
        
        assert is_valid is True

    async def test_validate_credentials_failure(self, resolver):
        """Test validating credentials when they don't exist."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint",
            auth=ApiKeyAuth(
                key_name="api_key",
                location="header"
            )
        )
        
        # Use empty storage
        temp_dir = tempfile.mkdtemp()
        empty_storage = LocalSecretStorage(temp_dir)
        
        try:
            with patch('runtime.core.credential_resolver.get_secret_storage', return_value=empty_storage):
                is_valid = await resolver.validate_credentials(tool, "nonexistent-connector")
        finally:
            shutil.rmtree(temp_dir)
        
        assert is_valid is False

    def test_redacted_summary(self):
        """Test that ResolvedCredentials provides redacted summary."""
        credentials = ResolvedCredentials(
            auth_type="api_key",
            headers={"authorization": "Bearer secret-token"},
            query_params={"api_key": "secret-key"},
            cookies={"session": "secret-session"}
        )
        
        summary = credentials.redacted_summary()
        
        assert summary["auth_type"] == "api_key"
        assert summary["has_headers"] is True
        assert summary["has_query_params"] is True
        assert summary["has_cookies"] is True
        assert summary["header_names"] == ["authorization"]
        assert summary["query_param_names"] == ["api_key"]
        assert summary["cookie_names"] == ["session"]
        
        # Ensure no actual secret values are in the summary
        summary_str = str(summary)
        assert "secret-token" not in summary_str
        assert "secret-key" not in summary_str
        assert "secret-session" not in summary_str


@pytest.mark.asyncio
class TestAuthenticatedHttpClient:
    """Tests for the AuthenticatedHttpClient class."""

    @pytest.fixture
    def client(self):
        """Create an authenticated HTTP client."""
        return AuthenticatedHttpClient()

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool for testing."""
        return ConnectorTool(
            name="test_api",
            description="Test API call",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="https://api.example.com/test",
            auth=ApiKeyAuth(
                key_name="x-api-key",
                location="header"
            )
        )

    async def test_authenticated_request(self, client, mock_tool):
        """Test making an authenticated HTTP request."""
        # Mock credential resolution
        mock_credentials = ResolvedCredentials(
            auth_type="api_key",
            headers={"x-api-key": "test-key-123"},
            query_params={},
            cookies={}
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        
        with patch('runtime.core.authenticated_client.get_credential_resolver') as mock_resolver, \
             patch('httpx.AsyncClient') as mock_client:
            
            mock_resolver.return_value.resolve_credentials = AsyncMock(return_value=mock_credentials)
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(return_value=mock_response)
            
            response = await client.request(
                method="GET",
                url="https://api.example.com/test",
                tool=mock_tool,
                connector_name="test-connector"
            )
        
        assert response == mock_response
        
        # Verify that credentials were applied
        mock_client.return_value.__aenter__.return_value.request.assert_called_once()
        call_args = mock_client.return_value.__aenter__.return_value.request.call_args
        assert call_args[1]["headers"]["x-api-key"] == "test-key-123"

    async def test_authenticated_request_credential_error(self, client, mock_tool):
        """Test authenticated request when credential resolution fails."""
        with patch('runtime.core.authenticated_client.get_credential_resolver') as mock_resolver:
            mock_resolver.return_value.resolve_credentials = AsyncMock(
                side_effect=CredentialResolutionError("No credentials found")
            )
            
            with pytest.raises(CredentialResolutionError, match="No credentials found"):
                await client.request(
                    method="GET",
                    url="https://api.example.com/test",
                    tool=mock_tool,
                    connector_name="test-connector"
                )


@pytest.mark.asyncio 
class TestToolExecutionClient:
    """Tests for the ToolExecutionClient class."""

    @pytest.fixture
    def execution_client(self):
        """Create a tool execution client."""
        reset_tool_execution_client()
        return ToolExecutionClient()

    @pytest.fixture
    def mock_tool(self):
        """Create a mock tool for testing."""
        return ConnectorTool(
            name="get_user",
            description="Get user information",
            input_schema={
                "type": "object",
                "properties": {
                    "username": {"type": "string"}
                },
                "required": ["username"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "username": {"type": "string"}
                }
            },
            endpoint="https://api.example.com/users/{username}",
            auth=ApiKeyAuth(
                key_name="authorization",
                location="header",
                scheme="Bearer"
            )
        )

    async def test_execute_tool_success(self, execution_client, mock_tool):
        """Test successful tool execution."""
        input_data = {"username": "testuser"}
        expected_response = {"id": 123, "username": "testuser"}
        
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = expected_response
        
        with patch.object(execution_client.http_client, 'request', return_value=mock_response) as mock_request:
            result = await execution_client.execute_tool(
                tool=mock_tool,
                connector_name="test-connector",
                input_data=input_data
            )
        
        assert result == expected_response
        mock_request.assert_called_once()
        
        # Verify URL parameter substitution
        call_args = mock_request.call_args
        assert "https://api.example.com/users/testuser" in call_args[1]["url"]

    async def test_execute_tool_input_validation_error(self, execution_client, mock_tool):
        """Test tool execution with invalid input."""
        # Missing required 'username' field
        invalid_input = {"invalid_field": "value"}
        
        with pytest.raises(ValueError, match="Input validation failed"):
            await execution_client.execute_tool(
                tool=mock_tool,
                connector_name="test-connector",
                input_data=invalid_input
            )

    async def test_execute_tool_http_error(self, execution_client, mock_tool):
        """Test tool execution with HTTP error."""
        input_data = {"username": "testuser"}
        
        # Mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        mock_response.request = MagicMock()
        
        with patch.object(execution_client.http_client, 'request', return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                await execution_client.execute_tool(
                    tool=mock_tool,
                    connector_name="test-connector",
                    input_data=input_data
                )

    def test_determine_http_method(self, execution_client):
        """Test HTTP method determination logic."""
        # Test GET (default)
        get_tool = ConnectorTool(
            name="get_user", description="Get user", input_schema={}, output_schema={}, endpoint="test", auth=NoAuth()
        )
        assert execution_client._determine_http_method(get_tool, {}) == "GET"
        
        # Test POST
        post_tool = ConnectorTool(
            name="create_user", description="Create user", input_schema={}, output_schema={}, endpoint="test", auth=NoAuth()
        )
        assert execution_client._determine_http_method(post_tool, {}) == "POST"
        
        # Test PUT  
        put_tool = ConnectorTool(
            name="update_user", description="Update user", input_schema={}, output_schema={}, endpoint="test", auth=NoAuth()
        )
        assert execution_client._determine_http_method(put_tool, {}) == "PUT"
        
        # Test DELETE
        delete_tool = ConnectorTool(
            name="delete_user", description="Delete user", input_schema={}, output_schema={}, endpoint="test", auth=NoAuth()
        )
        assert execution_client._determine_http_method(delete_tool, {}) == "DELETE"