"""
Pydantic models for MCP connector manifests.

This module defines the data models for connector descriptors used in the
MCP + "npm of APIs" platform. The models provide validation and serialization
for connector manifests in P0-1 phase.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator
import re
from jsonschema import Draft7Validator, ValidationError as JSONSchemaValidationError


class ApiKeyAuth(BaseModel):
    """API key authentication configuration."""
    type: Literal["api_key"] = Field(
        default="api_key",
        description="API key authentication type"
    )
    key_name: str = Field(
        ...,
        description="Name of the API key parameter (e.g., 'api_key', 'x-api-key')"
    )
    location: Literal["header", "query", "cookie"] = Field(
        default="header",
        description="Where the API key should be placed in requests"
    )
    scheme: Optional[str] = Field(
        default=None,
        description="Authentication scheme for header auth (e.g., 'Bearer', 'ApiKey')"
    )


class OAuth2ClientCredentialsAuth(BaseModel):
    """OAuth2 client credentials flow authentication."""
    type: Literal["oauth2_client_credentials"] = Field(
        default="oauth2_client_credentials",
        description="OAuth2 client credentials flow"
    )
    token_url: str = Field(
        ...,
        description="URL to obtain OAuth2 access token"
    )
    scopes: Optional[List[str]] = Field(
        default=None,
        description="List of OAuth2 scopes to request"
    )


class NoAuth(BaseModel):
    """No authentication required."""
    type: Literal["none"] = Field(
        default="none",
        description="No authentication required"
    )


class ToolAuth(BaseModel):
    """
    Authentication configuration for a tool.
    
    Supports multiple authentication types:
    - none: No authentication required
    - api_key: API key authentication (header, query, or cookie)
    - oauth2_client_credentials: OAuth2 client credentials flow
    """
    auth: Union[NoAuth, ApiKeyAuth, OAuth2ClientCredentialsAuth] = Field(
        default_factory=NoAuth,
        discriminator="type",
        description="Authentication configuration"
    )

    @property
    def type(self) -> str:
        """Get the authentication type."""
        return self.auth.type

    def is_authenticated(self) -> bool:
        """Check if authentication is required."""
        return self.auth.type != "none"

    def requires_credentials(self) -> bool:
        """Check if this auth type requires stored credentials."""
        return self.auth.type in ["api_key", "oauth2_client_credentials"]


class ConnectorTool(BaseModel):
    """
    Definition of a single tool within a connector.
    
    Each tool represents an API endpoint or logical operation that can be
    called by MCP clients (AI agents, LLMs).
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name for this tool within the connector"
    )
    
    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Human-readable description of what this tool does"
    )
    
    input_schema: Any = Field(
        ...,
        description="JSON Schema definition for tool input parameters"
    )
    
    output_schema: Any = Field(
        ...,
        description="JSON Schema definition for tool output format"
    )
    
    endpoint: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Logical endpoint name; maps to handler in MVP"
    )
    
    auth: Union[NoAuth, ApiKeyAuth, OAuth2ClientCredentialsAuth] = Field(
        default_factory=NoAuth,
        discriminator="type",
        description="Authentication configuration for this tool"
    )

    @property
    def auth_type(self) -> str:
        """Get the authentication type."""
        return self.auth.type

    def is_authenticated(self) -> bool:
        """Check if authentication is required."""
        return self.auth.type != "none"

    def requires_credentials(self) -> bool:
        """Check if this auth type requires stored credentials."""
        return self.auth.type in ["api_key", "oauth2_client_credentials"]

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate tool name follows naming conventions."""
        if not re.match(r'^[a-z][a-z0-9_]*$', v):
            raise ValueError(
                'Tool name must start with lowercase letter and contain only '
                'lowercase letters, numbers, and underscores'
            )
        return v

    @field_validator('endpoint')
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate endpoint follows naming conventions."""
        # Support two formats:
        # 1. HTTP method and path: "GET /path/{id}" or "POST /api/users"
        # 2. Legacy dot notation: "api.tool_name"
        
        # Check for HTTP method and path format
        if ' ' in v:
            parts = v.split(' ', 1)
            if len(parts) == 2:
                method, path = parts
                # Validate HTTP method
                if method.upper() not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']:
                    raise ValueError(
                        f'Invalid HTTP method "{method}". Must be one of: '
                        'GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS'
                    )
                # Validate path starts with /
                if not path.startswith('/'):
                    raise ValueError(f'API path "{path}" must start with "/"')
                return v
        
        # Fall back to legacy dot notation validation
        # - Start with letter
        # - Can contain letters, numbers, underscores, hyphens
        # - Dots are allowed but not consecutive and not at the end
        # - Each segment separated by dots must start with letter/number
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9_-]*)*$', v):
            raise ValueError(
                'Endpoint must either be HTTP format ("GET /path") or dot notation '
                '(start with letter, contain only letters, numbers, underscores, '
                'hyphens, and dots. No consecutive dots or ending dots allowed.)'
            )
        return v

    @field_validator('input_schema', 'output_schema')
    @classmethod
    def validate_json_schema(cls, v: Any) -> Dict[str, Any]:
        """Validate that schema is a valid JSON Schema."""
        # Check if it's a dictionary first
        if not isinstance(v, dict):
            raise ValueError("Schema must be a JSON object")
        
        # Cast to the expected type for validation
        schema_dict: Dict[str, Any] = v
        
        try:
            # Validate it's a valid JSON Schema
            Draft7Validator.check_schema(schema_dict)
            
            # Ensure it has required top-level properties
            # Allow $ref schemas (which don't require 'type') or schemas with 'type'
            if 'type' not in schema_dict and '$ref' not in schema_dict:
                raise ValueError("Schema must have either a 'type' property or a '$ref' property")
                
        except JSONSchemaValidationError as e:
            raise ValueError(f"Invalid JSON Schema: {e.message}")
        except Exception as e:
            raise ValueError(f"Schema validation error: {str(e)}")
        
        return schema_dict


class ConnectorManifest(BaseModel):
    """
    Complete connector manifest definition.
    
    This represents the YAML/JSON descriptor that defines a connector's
    capabilities, tools, and metadata for the MCP platform.
    """
    
    class Config:
        """Pydantic configuration."""
        # Allow extra fields for future extensibility
        extra = "forbid"
        # Use enum values for serialization
        use_enum_values = True
        # Validate assignment
        validate_assignment = True

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name identifier for the connector"
    )
    
    version: str = Field(
        ...,
        description="Semantic version of the connector (e.g., '1.0.0')"
    )
    
    tools: List[ConnectorTool] = Field(
        ...,
        min_length=1,
        max_length=50,  # Reasonable limit for P0-1
        description="List of tools provided by this connector"
    )
    
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL for the connector's API endpoints"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate connector name follows npm-like naming conventions."""
        # Allow scoped names like @org/connector-name
        # Must start with letter or @, not number
        pattern = r'^(@[a-z][a-z0-9-._~]*/)?[a-z][a-z0-9-._~]*$'
        if not re.match(pattern, v):
            raise ValueError(
                'Connector name must follow npm naming conventions: '
                'lowercase letters, numbers, hyphens, dots, underscores. '
                'Must start with letter. May include scope like @org/name'
            )
        return v

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate version follows semantic versioning."""
        # Basic semver pattern: major.minor.patch with optional pre-release/build
        pattern = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
        if not re.match(pattern, v):
            raise ValueError(
                'Version must follow semantic versioning (e.g., "1.0.0", "2.1.0-beta.1")'
            )
        return v

    @field_validator('tools')
    @classmethod
    def validate_unique_tool_names(cls, v: List[ConnectorTool]) -> List[ConnectorTool]:
        """Ensure all tool names are unique within the connector."""
        names = [tool.name for tool in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f'Duplicate tool names found: {set(duplicates)}')
        return v

    @field_validator('tools')
    @classmethod
    def validate_unique_endpoints(cls, v: List[ConnectorTool]) -> List[ConnectorTool]:
        """Ensure all endpoints are unique within the connector."""
        endpoints = [tool.endpoint for tool in v]
        if len(endpoints) != len(set(endpoints)):
            duplicates = [ep for ep in endpoints if endpoints.count(ep) > 1]
            raise ValueError(f'Duplicate endpoints found: {set(duplicates)}')
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary format."""
        return self.model_dump(by_alias=True, exclude_none=True)

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for YAML serialization."""
        data = self.to_dict()
        # Restructure for the expected YAML format
        connector_dict = {
            "name": data["name"],
            "version": data["version"],
            "tools": data["tools"]
        }
        
        # Include base_url if present
        if data.get("base_url"):
            connector_dict["base_url"] = data["base_url"]
            
        return {
            "connector": connector_dict
        }

    @classmethod
    def from_yaml_dict(cls, data: Dict[str, Any]) -> "ConnectorManifest":
        """Create manifest from YAML dictionary format."""
        if "connector" not in data:
            raise ValueError("YAML must have top-level 'connector' key")
        
        connector_data = data["connector"]
        return cls(**connector_data)

    def get_tool_by_name(self, name: str) -> Optional[ConnectorTool]:
        """Get a tool by its name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_tool_by_endpoint(self, endpoint: str) -> Optional[ConnectorTool]:
        """Get a tool by its endpoint."""
        for tool in self.tools:
            if tool.endpoint == endpoint:
                return tool
        return None

    def list_tool_names(self) -> List[str]:
        """Get list of all tool names in this connector."""
        return [tool.name for tool in self.tools]

    def validate_tool_input(self, tool_name: str, input_data: Dict[str, Any]) -> bool:
        """
        Validate input data against a tool's input schema.
        
        Args:
            tool_name: Name of the tool to validate against
            input_data: Input data to validate
            
        Returns:
            True if validation passes
            
        Raises:
            ValueError: If tool not found or validation fails
        """
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in connector")
        
        try:
            validator = Draft7Validator(tool.input_schema)
            validator.validate(input_data) # type: ignore
            return True
        except JSONSchemaValidationError as e:
            raise ValueError(f"Input validation failed for tool '{tool_name}': {e.message}")

    def validate_tool_output(self, tool_name: str, output_data: Dict[str, Any]) -> bool:
        """
        Validate output data against a tool's output schema.
        
        Args:
            tool_name: Name of the tool to validate against
            output_data: Output data to validate
            
        Returns:
            True if validation passes
            
        Raises:
            ValueError: If tool not found or validation fails
        """
        tool = self.get_tool_by_name(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found in connector")
        
        try:
            validator = Draft7Validator(tool.output_schema)
            validator.validate(output_data) # type: ignore
            return True
        except JSONSchemaValidationError as e:
            raise ValueError(f"Output validation failed for tool '{tool_name}': {e.message}")
