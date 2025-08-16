"""
Authenticated HTTP client for making external API calls.

This module provides an HTTP client that automatically applies authentication
credentials when making requests to external APIs based on connector tool
configurations.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Union
import httpx
import json

from .credential_resolver import get_credential_resolver, CredentialResolutionError, ResolvedCredentials
from models.manifest import ConnectorTool

logger = logging.getLogger(__name__)


class AuthenticatedHttpClient:
    """
    HTTP client that automatically applies authentication for connector tools.
    
    This client wraps httpx.AsyncClient and automatically resolves and applies
    authentication credentials based on the tool's auth configuration.
    """

    def __init__(self, timeout: float = 30.0, max_redirects: int = 5):
        """
        Initialize the authenticated HTTP client.
        
        Args:
            timeout: Request timeout in seconds
            max_redirects: Maximum number of redirects to follow
        """
        self.timeout = timeout
        self.max_redirects = max_redirects
        self._credential_resolver = get_credential_resolver()

    async def request(
        self,
        method: str,
        url: str,
        tool: ConnectorTool,
        connector_name: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make an authenticated HTTP request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            tool: Connector tool configuration
            connector_name: Name of the connector
            **kwargs: Additional arguments passed to httpx request
            
        Returns:
            httpx.Response object
            
        Raises:
            CredentialResolutionError: If credentials cannot be resolved
            httpx.HTTPError: If the HTTP request fails
        """
        try:
            # Resolve credentials for the tool
            credentials = await self._credential_resolver.resolve_credentials(tool, connector_name)
            
            # Prepare request parameters
            headers = kwargs.get("headers", {}).copy()
            params = kwargs.get("params", {}).copy()
            cookies = kwargs.get("cookies", {}).copy()
            
            # Apply resolved credentials
            headers.update(credentials.headers)
            params.update(credentials.query_params)
            cookies.update(credentials.cookies)
            
            # Update kwargs with authenticated parameters
            kwargs["headers"] = headers
            kwargs["params"] = params
            kwargs["cookies"] = cookies
            
            # Log request (with redacted credentials)
            logger.info(f"Making authenticated {method} request to {url}")
            logger.debug(f"Auth summary: {credentials.redacted_summary()}")
            
            # Make the request
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                max_redirects=self.max_redirects
            ) as client:
                response = await client.request(method, url, **kwargs)
                
                logger.info(f"Request completed: {response.status_code} {response.reason_phrase}")
                return response
                
        except CredentialResolutionError:
            logger.error(f"Failed to resolve credentials for {method} {url}")
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error for {method} {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {method} {url}: {e}")
            raise

    async def get(self, url: str, tool: ConnectorTool, connector_name: str, **kwargs) -> httpx.Response:
        """Make an authenticated GET request."""
        return await self.request("GET", url, tool, connector_name, **kwargs)

    async def post(self, url: str, tool: ConnectorTool, connector_name: str, **kwargs) -> httpx.Response:
        """Make an authenticated POST request."""
        return await self.request("POST", url, tool, connector_name, **kwargs)

    async def put(self, url: str, tool: ConnectorTool, connector_name: str, **kwargs) -> httpx.Response:
        """Make an authenticated PUT request."""
        return await self.request("PUT", url, tool, connector_name, **kwargs)

    async def delete(self, url: str, tool: ConnectorTool, connector_name: str, **kwargs) -> httpx.Response:
        """Make an authenticated DELETE request."""
        return await self.request("DELETE", url, tool, connector_name, **kwargs)

    async def patch(self, url: str, tool: ConnectorTool, connector_name: str, **kwargs) -> httpx.Response:
        """Make an authenticated PATCH request."""
        return await self.request("PATCH", url, tool, connector_name, **kwargs)


class ToolExecutionClient:
    """
    High-level client for executing connector tools with authentication.
    
    This client provides a convenient interface for executing connector tools
    with automatic credential resolution and HTTP request handling.
    """

    def __init__(self, http_client: Optional[AuthenticatedHttpClient] = None):
        """
        Initialize the tool execution client.
        
        Args:
            http_client: Optional HTTP client to use. If None, creates a default one.
        """
        self.http_client = http_client or AuthenticatedHttpClient()

    async def execute_tool(
        self,
        tool: ConnectorTool,
        connector_name: str,
        input_data: Dict[str, Any],
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a connector tool with authentication.
        
        Args:
            tool: Connector tool to execute
            connector_name: Name of the connector
            input_data: Input parameters for the tool
            base_url: Base URL for the API (if not included in endpoint)
            
        Returns:
            Tool execution result
            
        Raises:
            CredentialResolutionError: If credentials cannot be resolved
            ValueError: If input validation fails
            httpx.HTTPError: If the HTTP request fails
        """
        
        try:
            original_input_data = input_data.copy()
            self._validate_input_data(tool, input_data)
            if input_data != original_input_data:
                logger.debug(f"Input data was coerced during validation: {original_input_data} -> {input_data}")
            
            url = self._build_url(tool, base_url, input_data)
            method = self._determine_http_method(tool, input_data)
            
            request_kwargs = self._prepare_request_data(tool, input_data, method)
            
            # Make authenticated request
            response = await self.http_client.request(
                method=method,
                url=url,
                tool=tool,
                connector_name=connector_name,
                **request_kwargs
            )
            
            # Process response
            result = await self._process_response(tool, response)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute tool '{tool.name}': {e}")
            if hasattr(e, '__dict__'):
                logger.debug(f"Exception attributes: {e.__dict__}")
            raise

    def _validate_input_data(self, tool: ConnectorTool, input_data: Dict[str, Any]) -> None:
        """Validate input data against tool's input schema with automatic type conversion."""
        from jsonschema import Draft7Validator, ValidationError as JSONSchemaValidationError
        
        # First, apply type coercion based on schema
        coerced_data = self._coerce_input_types(tool, input_data)
        
        try:
            validator = Draft7Validator(tool.input_schema)
            validator.validate(coerced_data)
            
            # Update the original input_data dict with coerced values
            input_data.clear()
            input_data.update(coerced_data)
            
        except JSONSchemaValidationError as e:
            raise ValueError(f"Input validation failed for tool '{tool.name}': {e.message}")
    
    def _coerce_input_types(self, tool: ConnectorTool, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerce input data types based on the tool's input schema.
        
        This method automatically converts compatible types:
        - String numbers to integers/floats
        - String booleans to booleans
        - Other reasonable conversions
        """
        if not tool.input_schema or "properties" not in tool.input_schema:
            return input_data.copy()
        
        coerced_data = input_data.copy()
        properties = tool.input_schema.get("properties", {})
        
        for field_name, field_schema in properties.items():
            if field_name not in coerced_data:
                continue
                
            current_value = coerced_data[field_name]
            expected_type = field_schema.get("type")
            
            if expected_type and current_value is not None:
                try:
                    # Convert string to integer
                    if expected_type == "integer" and isinstance(current_value, str):
                        if current_value.isdigit() or (current_value.startswith('-') and current_value[1:].isdigit()):
                            coerced_data[field_name] = int(current_value)
                            logger.debug(f"Coerced '{field_name}' from string '{current_value}' to integer {coerced_data[field_name]}")
                    
                    # Convert string to number (float)
                    elif expected_type == "number" and isinstance(current_value, str):
                        try:
                            coerced_data[field_name] = float(current_value)
                            logger.debug(f"Coerced '{field_name}' from string '{current_value}' to number {coerced_data[field_name]}")
                        except ValueError:
                            pass  # Keep original value if conversion fails
                    
                    # Convert string to boolean
                    elif expected_type == "boolean" and isinstance(current_value, str):
                        lower_val = current_value.lower()
                        if lower_val in ("true", "1", "yes", "on"):
                            coerced_data[field_name] = True
                            logger.debug(f"Coerced '{field_name}' from string '{current_value}' to boolean True")
                        elif lower_val in ("false", "0", "no", "off"):
                            coerced_data[field_name] = False
                            logger.debug(f"Coerced '{field_name}' from string '{current_value}' to boolean False")
                    
                    # Convert integer to string
                    elif expected_type == "string" and isinstance(current_value, (int, float)):
                        coerced_data[field_name] = str(current_value)
                        logger.debug(f"Coerced '{field_name}' from {type(current_value).__name__} {current_value} to string '{coerced_data[field_name]}'")
                    
                    # Handle array types - convert single values to arrays if needed
                    elif expected_type == "array" and not isinstance(current_value, list):
                        coerced_data[field_name] = [current_value]
                        logger.debug(f"Coerced '{field_name}' from single value to array: {coerced_data[field_name]}")
                        
                except (ValueError, TypeError) as e:
                    # If conversion fails, log warning but keep original value
                    logger.warning(f"Failed to coerce '{field_name}' from {type(current_value).__name__} to {expected_type}: {e}")
                    
        return coerced_data

    def _build_url(self, tool: ConnectorTool, base_url: Optional[str], input_data: Dict[str, Any]) -> str:
        """Build the request URL from tool endpoint and input data."""
        logger.debug(f"Building URL for tool '{tool.name}' with endpoint '{tool.endpoint}'")
        
        # Extract the path from the endpoint by removing HTTP method prefix if present
        endpoint = tool.endpoint
        path_part = endpoint
        
        # Check if endpoint starts with an HTTP method (GET, POST, PUT, DELETE, PATCH)
        http_methods = ["GET ", "POST ", "PUT ", "DELETE ", "PATCH "]
        for method in http_methods:
            if endpoint.startswith(method):
                path_part = endpoint[len(method):].strip()
                logger.debug(f"Stripped HTTP method '{method.strip()}' from endpoint, path part: '{path_part}'")
                break
        
        if path_part.startswith("http"):
            # Endpoint is a full URL
            url = path_part
            logger.debug(f"Using endpoint as full URL: {url}")
        elif base_url:
            # Append path to base URL
            url = f"{base_url.rstrip('/')}/{path_part.lstrip('/')}"
            logger.debug(f"Combined base_url '{base_url}' with path '{path_part}' to get: {url}")
        else:
            logger.error(f"Cannot build URL for tool '{tool.name}': no base URL provided and endpoint is not a full URL")
            raise ValueError(f"Cannot build URL for tool '{tool.name}': no base URL provided")
        
        # Simple URL parameter substitution (MVP implementation)
        # In a full implementation, this would be more sophisticated
        original_url = url
        for key, value in input_data.items():
            placeholder = f"{{{key}}}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))
                logger.debug(f"Replaced placeholder '{placeholder}' with '{value}' in URL")
        
        if url != original_url:
            logger.debug(f"URL after parameter substitution: {url}")
        
        return url

    def _determine_http_method(self, tool: ConnectorTool, input_data: Dict[str, Any]) -> str:
        """Determine HTTP method for the tool (MVP implementation)."""
        # For MVP, infer method from tool name/endpoint
        tool_name_lower = tool.name.lower()
        logger.debug(f"Determining HTTP method for tool '{tool.name}' (lowercase: '{tool_name_lower}')")
        
        if any(verb in tool_name_lower for verb in ["create", "add", "post", "submit"]):
            method = "POST"
            logger.debug(f"Detected create/add/post/submit verb in tool name, using POST method")
        elif any(verb in tool_name_lower for verb in ["update", "edit", "modify"]):
            method = "PUT"
            logger.debug(f"Detected update/edit/modify verb in tool name, using PUT method")
        elif any(verb in tool_name_lower for verb in ["delete", "remove"]):
            method = "DELETE"
            logger.debug(f"Detected delete/remove verb in tool name, using DELETE method")
        else:
            method = "GET"
            logger.debug(f"No specific verb detected in tool name, defaulting to GET method")
        
        return method

    def _prepare_request_data(self, tool: ConnectorTool, input_data: Dict[str, Any], method: str) -> Dict[str, Any]:
        """Prepare request data based on HTTP method."""
        logger.debug(f"Preparing request data for method '{method}' with input data: {input_data}")
        
        kwargs = {}
        
        if method in ["POST", "PUT", "PATCH"]:
            # For write operations, send data as JSON body
            kwargs["json"] = input_data
            kwargs["headers"] = {"Content-Type": "application/json"}
            logger.debug(f"Using JSON body for {method} request: {input_data}")
        else:
            # For read operations, check if any parameters are path parameters
            # Path parameters are those that appear in the endpoint as {paramName}
            endpoint = tool.endpoint
            
            # Extract path part from endpoint (remove HTTP method if present)
            path_part = endpoint
            http_methods = ["GET ", "POST ", "PUT ", "DELETE ", "PATCH "]
            for http_method in http_methods:
                if endpoint.startswith(http_method):
                    path_part = endpoint[len(http_method):].strip()
                    break
            
            # Identify path parameters by looking for {paramName} patterns
            import re
            path_params = set(re.findall(r'\{(\w+)\}', path_part))
            logger.debug(f"Identified path parameters from endpoint '{path_part}': {path_params}")
            
            # Only include non-path parameters as query parameters
            query_params = {k: v for k, v in input_data.items() if k not in path_params}
            
            if query_params:
                kwargs["params"] = query_params
                logger.debug(f"Using query parameters for {method} request: {query_params}")
            else:
                logger.debug(f"No query parameters needed for {method} request (all parameters are path parameters)")
        
        logger.debug(f"Prepared request kwargs: {kwargs}")
        return kwargs

    async def _process_response(self, tool: ConnectorTool, response: httpx.Response) -> Dict[str, Any]:
        """Process HTTP response and validate against tool's output schema."""
        # Check response status
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                message=f"HTTP {response.status_code}: {response.reason_phrase}",
                request=response.request,
                response=response
            )
        
        # Parse response data
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                result_data = response.json()
            else:
                # For non-JSON responses, wrap in a simple structure
                result_data = {
                    "content": response.text,
                    "content_type": response.headers.get("content-type", ""),
                    "status_code": response.status_code
                }
        except json.JSONDecodeError:
            # If JSON parsing fails, return text content
            result_data = {
                "content": response.text,
                "content_type": response.headers.get("content-type", ""),
                "status_code": response.status_code
            }
        
        # Validate against output schema (optional for MVP)
        try:
            self._validate_output_data(tool, result_data)
        except ValueError as e:
            # Log validation error but don't fail the request
            logger.warning(f"Output validation failed for tool '{tool.name}': {e}")
        
        return result_data

    def _validate_output_data(self, tool: ConnectorTool, output_data: Dict[str, Any]) -> None:
        """Validate output data against tool's output schema."""
        from jsonschema import Draft7Validator, ValidationError as JSONSchemaValidationError
        
        try:
            validator = Draft7Validator(tool.output_schema)
            validator.validate(output_data)
        except JSONSchemaValidationError as e:
            raise ValueError(f"Output validation failed for tool '{tool.name}': {e.message}")


# Global tool execution client instance
_tool_execution_client: Optional[ToolExecutionClient] = None


def get_tool_execution_client() -> ToolExecutionClient:
    """
    Get the global tool execution client instance.
    
    Returns:
        ToolExecutionClient instance
    """
    global _tool_execution_client
    
    if _tool_execution_client is None:
        _tool_execution_client = ToolExecutionClient()
    
    return _tool_execution_client


def reset_tool_execution_client() -> None:
    """Reset the global tool execution client instance (useful for testing)."""
    global _tool_execution_client
    _tool_execution_client = None