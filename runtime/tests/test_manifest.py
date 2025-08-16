"""
Tests for connector manifest models.

This module contains comprehensive tests for the Pydantic models
used to validate and process connector manifests.
"""

from typing import Dict, Any
import pytest
import sys
import os
# Import the specific ValidationError type that's actually raised
from pydantic_core import ValidationError

# Add the parent directory to the path for package imports
runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(runtime_dir)
sys.path.insert(0, parent_dir)

from runtime.models.manifest import (
    ConnectorManifest, 
    ConnectorTool, 
    NoAuth, 
    ApiKeyAuth, 
    OAuth2ClientCredentialsAuth
)


class TestToolAuth:
    """Tests for individual auth models."""

    def test_no_auth(self):
        """Test NoAuth model."""
        auth = NoAuth()
        assert auth.type == "none"

    def test_api_key_auth(self):
        """Test ApiKeyAuth model."""
        auth = ApiKeyAuth(
            key_name="x-api-key",
            location="header"
        )
        assert auth.type == "api_key"
        assert auth.key_name == "x-api-key"
        assert auth.location == "header"
        assert auth.scheme is None

    def test_api_key_auth_with_scheme(self):
        """Test ApiKeyAuth with scheme."""
        auth = ApiKeyAuth(
            key_name="authorization",
            location="header",
            scheme="Bearer"
        )
        assert auth.type == "api_key"
        assert auth.scheme == "Bearer"

    def test_oauth2_client_credentials_auth(self):
        """Test OAuth2ClientCredentialsAuth model."""
        auth = OAuth2ClientCredentialsAuth(
            token_url="https://api.example.com/oauth/token",
            scopes=["read", "write"]
        )
        assert auth.type == "oauth2_client_credentials"
        assert auth.token_url == "https://api.example.com/oauth/token"
        assert auth.scopes == ["read", "write"]


class TestConnectorToolAuth:
    """Tests for ConnectorTool auth functionality."""

    def test_tool_default_auth(self):
        """Test that tools default to no authentication."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint"
        )
        assert tool.auth_type == "none"
        assert not tool.is_authenticated()
        assert not tool.requires_credentials()

    def test_tool_api_key_auth(self):
        """Test tool with API key authentication."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint",
            auth={
                "type": "api_key",
                "key_name": "x-api-key",
                "location": "header"
            }
        )
        assert tool.auth_type == "api_key"
        assert tool.is_authenticated()
        assert tool.requires_credentials()
        assert tool.auth.key_name == "x-api-key"

    def test_tool_oauth2_auth(self):
        """Test tool with OAuth2 authentication."""
        tool = ConnectorTool(
            name="test_tool",
            description="Test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            endpoint="test.endpoint",
            auth={
                "type": "oauth2_client_credentials",
                "token_url": "https://api.example.com/oauth/token",
                "scopes": ["read"]
            }
        )
        assert tool.auth_type == "oauth2_client_credentials"
        assert tool.is_authenticated()
        assert tool.requires_credentials()
        assert tool.auth.token_url == "https://api.example.com/oauth/token"


class TestConnectorTool:
    """Tests for ConnectorTool model."""

    @pytest.fixture
    def valid_tool_data(self) -> Dict[str, Any]:
        """Valid tool data for testing."""
        return {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "units": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "temperature": {"type": "number"},
                    "description": {"type": "string"},
                    "humidity": {"type": "number"}
                },
                "required": ["temperature", "description"]
            },
            "endpoint": "weather.get_current"
        }

    def test_valid_tool_creation(self, valid_tool_data: Dict[str, Any]):
        """Test creating a valid tool."""
        tool = ConnectorTool(**valid_tool_data)
        assert tool.name == "get_weather"
        assert tool.description == "Get current weather for a location"
        assert tool.endpoint == "weather.get_current"
        assert tool.auth.type == "none"

    def test_tool_name_validation(self, valid_tool_data: Dict[str, Any]):
        """Test tool name validation rules."""
        # Valid names
        valid_names = ["get_weather", "list_items", "create_user", "api_v2"]
        for name in valid_names:
            data = valid_tool_data.copy()
            data["name"] = name
            tool = ConnectorTool(**data)
            assert tool.name == name

        # Invalid names - check against actual validator pattern
        invalid_names = [
            "GetWeather",  # uppercase
            "get-weather",  # hyphen (not allowed in tool names)
            "2get_weather",  # starts with number
            "get weather",  # space
            "",  # empty
            "a" * 101  # too long
        ]
        for name in invalid_names:
            data = valid_tool_data.copy()
            data["name"] = name
            with pytest.raises(ValidationError):
                ConnectorTool(**data)

    def test_endpoint_validation(self, valid_tool_data: Dict[str, Any]):
        """Test endpoint validation rules."""
        # Valid endpoints
        valid_endpoints = [
            "weather.get",
            "api-v1.users",
            "service_name.action",
            "simple",
            "Complex.Multi-Part.endpoint_name"
        ]
        for endpoint in valid_endpoints:
            data = valid_tool_data.copy()
            data["endpoint"] = endpoint
            tool = ConnectorTool(**data)
            assert tool.endpoint == endpoint

        # Invalid endpoints
        invalid_endpoints = [
            "1weather",  # starts with number
            "-weather",  # starts with hyphen
            "weather..get",  # double dot
            "weather.",  # ends with dot
            "",  # empty
            "a" * 201  # too long
        ]
        for endpoint in invalid_endpoints:
            data = valid_tool_data.copy()
            data["endpoint"] = endpoint
            with pytest.raises(ValidationError):
                ConnectorTool(**data)

    def test_schema_validation(self, valid_tool_data: Dict[str, Any]):
        """Test JSON schema validation."""
        # Invalid schema - not an object
        data = valid_tool_data.copy()
        data["input_schema"] = "not a schema"
        with pytest.raises(ValidationError) as exc_info:
            ConnectorTool(**data)
        assert "Schema must be a JSON object" in str(exc_info.value)

        # Invalid schema - missing type
        data = valid_tool_data.copy()
        data["input_schema"] = {"properties": {}}
        with pytest.raises(ValidationError) as exc_info:
            ConnectorTool(**data)
        assert "Schema must have a 'type' property" in str(exc_info.value)

        # Invalid JSON Schema
        data = valid_tool_data.copy()
        data["input_schema"] = {"type": "invalid_type"}
        with pytest.raises(ValidationError) as exc_info:
            ConnectorTool(**data)
        assert "Schema validation error" in str(exc_info.value)

    def test_description_length_validation(self, valid_tool_data: Dict[str, Any]):
        """Test description length validation."""
        # Empty description
        data = valid_tool_data.copy()
        data["description"] = ""
        with pytest.raises(ValidationError):
            ConnectorTool(**data)

        # Too long description
        data = valid_tool_data.copy()
        data["description"] = "a" * 1001
        with pytest.raises(ValidationError):
            ConnectorTool(**data)


class TestConnectorManifest:
    """Tests for ConnectorManifest model."""

    @pytest.fixture
    def valid_manifest_data(self) -> Dict[str, Any]:
        """Valid manifest data for testing."""
        return {
            "name": "weather-api",
            "version": "1.0.0",
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get current weather for a location",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        },
                        "required": ["location"]
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "temperature": {"type": "number"}
                        },
                        "required": ["temperature"]
                    },
                    "endpoint": "weather.get"
                },
                {
                    "name": "get_forecast",
                    "description": "Get weather forecast",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"},
                            "days": {"type": "integer", "minimum": 1, "maximum": 7}
                        },
                        "required": ["location"]
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "forecast": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "date": {"type": "string"},
                                        "temperature": {"type": "number"}
                                    }
                                }
                            }
                        },
                        "required": ["forecast"]
                    },
                    "endpoint": "weather.forecast"
                }
            ]
        }

    def test_valid_manifest_creation(self, valid_manifest_data: Dict[str, Any]):
        """Test creating a valid manifest."""
        manifest = ConnectorManifest(**valid_manifest_data)
        assert manifest.name == "weather-api"
        assert manifest.version == "1.0.0"
        assert len(manifest.tools) == 2
        assert manifest.tools[0].name == "get_weather"
        assert manifest.tools[1].name == "get_forecast"

    def test_connector_name_validation(self, valid_manifest_data: Dict[str, Any]):
        """Test connector name validation rules."""
        # Valid names
        valid_names = [
            "weather-api",
            "weather_api",
            "weather.api",
            "api123",
            "@org/weather-api",
            "@my-org/weather.connector",
            "simple"
        ]
        for name in valid_names:
            data = valid_manifest_data.copy()
            data["name"] = name
            manifest = ConnectorManifest(**data)
            assert manifest.name == name

        # Invalid names
        invalid_names = [
            "Weather-API",  # uppercase
            "weather API",  # space
            "",  # empty
            "123weather",  # starts with number
            "@/weather",  # invalid scope
            "@ORG/weather",  # uppercase in scope
            "a" * 101  # too long
        ]
        for name in invalid_names:
            data = valid_manifest_data.copy()
            data["name"] = name
            with pytest.raises(ValidationError):
                ConnectorManifest(**data)

    def test_version_validation(self, valid_manifest_data: Dict[str, Any]):
        """Test semantic version validation."""
        # Valid versions
        valid_versions = [
            "1.0.0",
            "0.1.0",
            "10.20.30",
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-0.3.7",
            "1.0.0-x.7.z.92",
            "1.0.0+20130313144700",
            "1.0.0-beta+exp.sha.5114f85"
        ]
        for version in valid_versions:
            data = valid_manifest_data.copy()
            data["version"] = version
            manifest = ConnectorManifest(**data)
            assert manifest.version == version

        # Invalid versions
        invalid_versions = [
            "1",
            "1.0",
            "1.0.0.0",
            "v1.0.0",
            "1.0.0-",
            "1.0.0+",
            "",
            "not.a.version"
        ]
        for version in invalid_versions:
            data = valid_manifest_data.copy()
            data["version"] = version
            with pytest.raises(ValidationError):
                ConnectorManifest(**data)

    def test_tools_validation(self, valid_manifest_data: Dict[str, Any]):
        """Test tools list validation."""
        # Empty tools list
        data = valid_manifest_data.copy()
        data["tools"] = []
        with pytest.raises(ValidationError) as exc_info:
            ConnectorManifest(**data)
        assert "at least 1 item" in str(exc_info.value)

        # Too many tools
        data = valid_manifest_data.copy()
        tool_template = data["tools"][0].copy()
        data["tools"] = []
        for i in range(51):  # exceeds max of 50
            tool = tool_template.copy()
            tool["name"] = f"tool_{i}"
            tool["endpoint"] = f"endpoint_{i}"
            data["tools"].append(tool)
        
        with pytest.raises(ValidationError) as exc_info:
            ConnectorManifest(**data)
        assert "at most 50 items" in str(exc_info.value)

    def test_unique_tool_names(self, valid_manifest_data):
        """Test that tool names must be unique."""
        data = valid_manifest_data.copy()
        # Make both tools have the same name
        data["tools"][1]["name"] = data["tools"][0]["name"]
        
        with pytest.raises(ValidationError) as exc_info:
            ConnectorManifest(**data)
        assert "Duplicate tool names" in str(exc_info.value)

    def test_unique_endpoints(self, valid_manifest_data):
        """Test that endpoints must be unique."""
        data = valid_manifest_data.copy()
        # Make both tools have the same endpoint
        data["tools"][1]["endpoint"] = data["tools"][0]["endpoint"]
        
        with pytest.raises(ValidationError) as exc_info:
            ConnectorManifest(**data)
        assert "Duplicate endpoints" in str(exc_info.value)

    def test_yaml_format_conversion(self, valid_manifest_data):
        """Test conversion to/from YAML format."""
        manifest = ConnectorManifest(**valid_manifest_data)
        
        # Convert to YAML format
        yaml_dict = manifest.to_yaml_dict()
        assert "connector" in yaml_dict
        assert yaml_dict["connector"]["name"] == "weather-api"
        assert yaml_dict["connector"]["version"] == "1.0.0"
        assert len(yaml_dict["connector"]["tools"]) == 2

        # Convert back from YAML format
        manifest2 = ConnectorManifest.from_yaml_dict(yaml_dict)
        assert manifest2.name == manifest.name
        assert manifest2.version == manifest.version
        assert len(manifest2.tools) == len(manifest.tools)

    def test_yaml_format_invalid(self):
        """Test error handling for invalid YAML format."""
        invalid_yaml = {"invalid": "structure"}
        
        with pytest.raises(ValueError) as exc_info:
            ConnectorManifest.from_yaml_dict(invalid_yaml)
        assert "YAML must have top-level 'connector' key" in str(exc_info.value)

    def test_tool_lookup_methods(self, valid_manifest_data):
        """Test tool lookup methods."""
        manifest = ConnectorManifest(**valid_manifest_data)
        
        # Test get_tool_by_name
        tool = manifest.get_tool_by_name("get_weather")
        assert tool is not None
        assert tool.name == "get_weather"
        
        tool = manifest.get_tool_by_name("nonexistent")
        assert tool is None
        
        # Test get_tool_by_endpoint
        tool = manifest.get_tool_by_endpoint("weather.get")
        assert tool is not None
        assert tool.endpoint == "weather.get"
        
        tool = manifest.get_tool_by_endpoint("nonexistent")
        assert tool is None
        
        # Test list_tool_names
        names = manifest.list_tool_names()
        assert names == ["get_weather", "get_forecast"]

    def test_input_validation(self, valid_manifest_data):
        """Test tool input validation."""
        manifest = ConnectorManifest(**valid_manifest_data)
        
        # Valid input
        valid_input = {"location": "New York"}
        assert manifest.validate_tool_input("get_weather", valid_input) is True
        
        # Invalid input - missing required field
        invalid_input = {}
        with pytest.raises(ValueError) as exc_info:
            manifest.validate_tool_input("get_weather", invalid_input)
        assert "Input validation failed" in str(exc_info.value)
        
        # Nonexistent tool
        with pytest.raises(ValueError) as exc_info:
            manifest.validate_tool_input("nonexistent", valid_input)
        assert "Tool 'nonexistent' not found" in str(exc_info.value)

    def test_output_validation(self, valid_manifest_data):
        """Test tool output validation."""
        manifest = ConnectorManifest(**valid_manifest_data)
        
        # Valid output
        valid_output = {"temperature": 25.5}
        assert manifest.validate_tool_output("get_weather", valid_output) is True
        
        # Invalid output - missing required field
        invalid_output = {"humidity": 60}
        with pytest.raises(ValueError) as exc_info:
            manifest.validate_tool_output("get_weather", invalid_output)
        assert "Output validation failed" in str(exc_info.value)
        
        # Nonexistent tool
        with pytest.raises(ValueError) as exc_info:
            manifest.validate_tool_output("nonexistent", valid_output)
        assert "Tool 'nonexistent' not found" in str(exc_info.value)
