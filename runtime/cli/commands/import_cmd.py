"""
MCP import command implementation.

This command imports OpenAPI specifications and converts them to MCP connector manifests.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import re

import click
import yaml
import requests
from prance import ResolvingParser
from openapi_spec_validator import validate_spec
from openapi_spec_validator.exceptions import OpenAPISpecValidatorError

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_dir))

from models.manifest import ConnectorManifest, ConnectorTool, ToolAuth


@click.command(
    name="import",
    help="Import OpenAPI specification and generate MCP connector manifest."
)
@click.argument(
    "openapi_source",
    type=str,
    required=True
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    help="Output file path for generated manifest (default: saved to samples directory)"
)
@click.option(
    "--name", "-n",
    type=str,
    help="Override connector name (default: derived from OpenAPI info)"
)
@click.option(
    "--version", "-v",
    type=str,
    help="Override connector version (default: derived from OpenAPI info)"
)
@click.option(
    "--include-path", "-i",
    multiple=True,
    help="Include only paths matching this pattern (can be used multiple times)"
)
@click.option(
    "--exclude-path", "-e",
    multiple=True,
    help="Exclude paths matching this pattern (can be used multiple times)"
)
@click.option(
    "--max-tools",
    type=int,
    default=50,
    help="Maximum number of tools to generate (default: 50)"
)
@click.option(
    "--force", "-f",
    is_flag=True,
    help="Overwrite output file if it exists"
)
@click.option(
    "--validate",
    is_flag=True,
    help="Validate generated manifest before saving"
)
@click.pass_context
def import_command(
    ctx: click.Context,
    openapi_source: str,
    output: Optional[Path],
    name: Optional[str],
    version: Optional[str],
    include_path: tuple[str, ...],
    exclude_path: tuple[str, ...],
    max_tools: int,
    force: bool,
    validate: bool
) -> None:
    """
    Import OpenAPI specification and generate MCP connector manifest.
    
    OPENAPI_SOURCE can be:
    - Local file path (JSON or YAML)
    - HTTP/HTTPS URL to OpenAPI spec
    - '-' to read from stdin
    
    Examples:
      mcp import https://api.example.com/openapi.json
      mcp import ./my-api.yaml --name "@myorg/my-api" --output my-connector.yaml
      mcp import spec.json --include-path "/users/*" --exclude-path "/admin/*"
    """
    verbose = ctx.obj.get('verbose', False)
    
    if verbose:
        click.echo(f"Importing OpenAPI specification from: {openapi_source}")
    
    try:
        # Step 1: Load OpenAPI specification
        spec_data = load_openapi_spec(openapi_source, verbose)
        
        # Step 2: Resolve references in the OpenAPI spec
        if verbose:
            click.echo("Resolving OpenAPI references...")
        resolved_spec = resolve_openapi_references(spec_data, verbose)
        
        # Step 3: Validate OpenAPI specification
        if verbose:
            click.echo("Validating OpenAPI specification...")
        try:
            validate_openapi_spec(resolved_spec)
            if verbose:
                click.echo("✓ OpenAPI specification is valid")
        except Exception as validation_error:
            click.echo(click.style(f"⚠ Warning: OpenAPI validation failed - {validation_error}", fg='yellow'))
            click.echo("This is common with real-world APIs. Continuing with conversion...")
        
        # Step 4: Convert to MCP manifest
        if verbose:
            click.echo("Converting to MCP connector manifest...")
        manifest = convert_openapi_to_mcp(
            resolved_spec, 
            name_override=name,
            version_override=version,
            include_patterns=list(include_path),
            exclude_patterns=list(exclude_path),
            max_tools=max_tools,
            source_url=openapi_source,  # Pass source URL for base URL inference
            verbose=verbose
        )
        
        # Step 5: Validate generated manifest if requested
        if validate:
            if verbose:
                click.echo("Validating generated manifest...")
            try:
                # Test that the manifest is valid
                test_manifest = ConnectorManifest.from_yaml_dict(manifest)
                click.echo(click.style("✓ Generated manifest is valid", fg='green'))
            except Exception as e:
                click.echo(click.style(f"✗ Generated manifest validation failed: {e}", fg='red'))
                sys.exit(1)
        
        # Step 6: Determine output path
        if not output:
            connector_name = manifest["connector"]["name"]
            # Clean connector name for filename
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', connector_name)
            
            # Save to samples directory by default
            samples_dir = parent_dir / "samples"
            samples_dir.mkdir(exist_ok=True)  # Ensure samples directory exists
            output = samples_dir / f"{safe_name}.yaml"
        
        # Step 7: Check if output file exists
        if output.exists() and not force:
            click.echo(click.style(f"Output file {output} already exists. Use --force to overwrite.", fg='red'))
            sys.exit(1)
        
        # Step 8: Save manifest
        with open(output, 'w', encoding='utf-8') as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False, indent=2)
        
        # Step 9: Success message
        tools_count = len(manifest["connector"]["tools"])
        click.echo(click.style(f"✓ Successfully generated MCP connector manifest!", fg='green', bold=True))
        click.echo(f"  Output file: {output}")
        click.echo(f"  Saved to samples directory: {output.relative_to(parent_dir)}")
        click.echo(f"  Connector name: {manifest['connector']['name']}")
        click.echo(f"  Connector version: {manifest['connector']['version']}")
        click.echo(f"  Tools generated: {tools_count}")
        
        if verbose:
            click.echo("\nGenerated tools:")
            for tool in manifest["connector"]["tools"]:
                click.echo(f"  - {tool['name']} ({tool['endpoint']})")
        
    except Exception as e:
        click.echo(click.style(f"✗ Import failed: {str(e)}", fg='red'))
        if verbose:
            import traceback
            click.echo(traceback.format_exc())
        sys.exit(1)


def load_openapi_spec(source: str, verbose: bool) -> Dict[str, Any]:
    """
    Load OpenAPI specification from various sources.
    
    Args:
        source: File path, URL, or '-' for stdin
        verbose: Whether to show verbose output
        
    Returns:
        Parsed OpenAPI specification as dictionary
    """
    if verbose:
        click.echo(f"  Loading from source: {source}")
    
    if source == '-':
        # Read from stdin
        content = sys.stdin.read()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return yaml.safe_load(content)
    
    elif source.startswith(('http://', 'https://')):
        # Fetch from URL
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        if 'json' in content_type:
            return response.json()
        else:
            return yaml.safe_load(response.text)
    
    else:
        # Load from local file
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"OpenAPI file not found: {source}")
        
        with open(source_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to determine format from extension or content
        if source_path.suffix.lower() == '.json':
            return json.loads(content)
        else:
            return yaml.safe_load(content)


def resolve_openapi_references(spec_data: Dict[str, Any], verbose: bool) -> Dict[str, Any]:
    """
    Resolve $ref references in OpenAPI specification.
    
    Args:
        spec_data: OpenAPI specification dictionary
        verbose: Whether to show verbose output
        
    Returns:
        Resolved OpenAPI specification
    """
    try:
        # Create a copy to avoid modifying the original
        import copy
        resolved_spec = copy.deepcopy(spec_data)
        
        # Get components/schemas for reference resolution
        components = spec_data.get('components', {})
        schemas = components.get('schemas', {})
        
        if verbose and schemas:
            click.echo(f"  Found {len(schemas)} component schemas to resolve")
        
        # Recursively resolve $ref references
        def resolve_refs(obj):
            if isinstance(obj, dict):
                if '$ref' in obj:
                    ref_path = obj['$ref']
                    if ref_path.startswith('#/components/schemas/'):
                        schema_name = ref_path.split('/')[-1]
                        if schema_name in schemas:
                            # Return the resolved schema instead of the reference
                            resolved_schema = resolve_refs(schemas[schema_name])
                            return resolved_schema
                        else:
                            # Keep the reference if we can't resolve it
                            return obj
                    else:
                        # Non-component reference, keep as is
                        return obj
                else:
                    # Recursively process all values
                    return {k: resolve_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_refs(item) for item in obj]
            else:
                return obj
        
        # Resolve references in the entire spec
        resolved_spec = resolve_refs(resolved_spec)
        
        if verbose:
            click.echo(f"  Successfully resolved schema references")
        
        return resolved_spec
        
    except Exception as e:
        if verbose:
            click.echo(f"  Warning: Could not resolve references: {e}")
        return spec_data


def validate_openapi_spec(spec_data: Dict[str, Any]) -> None:
    """
    Validate OpenAPI specification using openapi-spec-validator.
    
    Args:
        spec_data: OpenAPI specification dictionary
        
    Raises:
        OpenAPISpecValidatorError: If specification is invalid
    """
    try:
        # Clean up common issues before validation
        cleaned_spec = clean_openapi_spec(spec_data)
        validate_spec(cleaned_spec)
    except OpenAPISpecValidatorError as e:
        raise ValueError(f"Invalid OpenAPI specification: {e}")


def clean_openapi_spec(spec_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean up common issues in OpenAPI specifications.
    
    Args:
        spec_data: OpenAPI specification dictionary
        
    Returns:
        Cleaned OpenAPI specification
    """
    import copy
    cleaned_spec = copy.deepcopy(spec_data)
    
    # Fix empty security arrays - common issue with many APIs
    if 'security' in cleaned_spec:
        security = cleaned_spec['security']
        if isinstance(security, list):
            # Remove empty arrays from security list
            cleaned_security = [item for item in security if item != []]
            if not cleaned_security:
                # If all items were empty arrays, remove security entirely
                del cleaned_spec['security']
            else:
                cleaned_spec['security'] = cleaned_security
    
    # Fix paths with empty security arrays
    paths = cleaned_spec.get('paths', {})
    for path_key, path_item in paths.items():
        if isinstance(path_item, dict):
            for method_key, operation in path_item.items():
                if isinstance(operation, dict) and 'security' in operation:
                    security = operation['security']
                    if isinstance(security, list):
                        # Remove empty arrays from operation security
                        cleaned_security = [item for item in security if item != []]
                        if not cleaned_security:
                            del operation['security']
                        else:
                            operation['security'] = cleaned_security
    
    return cleaned_spec


def extract_base_url(spec_data: Dict[str, Any], source_url: Optional[str], verbose: bool) -> Optional[str]:
    """
    Extract base URL from OpenAPI specification.
    
    Args:
        spec_data: OpenAPI specification dictionary
        source_url: URL where the spec was loaded from (for inference)
        verbose: Whether to show verbose output
        
    Returns:
        Base URL string or None if not found
    """
    # Try OpenAPI 3.x servers first
    servers = spec_data.get('servers', [])
    if servers and isinstance(servers, list) and len(servers) > 0:
        server = servers[0]
        if isinstance(server, dict) and 'url' in server:
            base_url = server['url']
            if verbose:
                click.echo(f"  Found OpenAPI 3.x server URL: {base_url}")
            return base_url
    
    # Fall back to Swagger 2.0 format
    host = spec_data.get('host')
    base_path = spec_data.get('basePath', '')
    schemes = spec_data.get('schemes', ['https'])
    
    if host:
        # Use first scheme (prefer https if available)
        scheme = 'https' if 'https' in schemes else schemes[0]
        base_url = f"{scheme}://{host}{base_path}"
        if verbose:
            click.echo(f"  Built base URL from Swagger 2.0: {base_url}")
        return base_url
    
    # Try to infer from source URL if it's a URL
    if source_url and source_url.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(source_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        if verbose:
            click.echo(f"  Inferred base URL from source: {base_url}")
        return base_url
    
    if verbose:
        click.echo("  No base URL found in OpenAPI specification")
    return None


def convert_openapi_to_mcp(
    spec_data: Dict[str, Any],
    name_override: Optional[str] = None,
    version_override: Optional[str] = None,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_tools: int = 50,
    source_url: Optional[str] = None,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Convert OpenAPI specification to MCP connector manifest.
    
    Args:
        spec_data: OpenAPI specification dictionary
        name_override: Override for connector name
        version_override: Override for connector version
        include_patterns: Patterns for paths to include
        exclude_patterns: Patterns for paths to exclude
        max_tools: Maximum number of tools to generate
        verbose: Whether to show verbose output
        
    Returns:
        MCP connector manifest dictionary
    """
    info = spec_data.get('info', {})
    
    # Determine connector name
    if name_override:
        connector_name = name_override
    else:
        title = info.get('title', 'Unknown API')
        # Convert to npm-style name
        connector_name = title.lower().replace(' ', '-').replace('_', '-')
        # Remove special characters
        connector_name = re.sub(r'[^a-z0-9-]', '', connector_name)
        if not connector_name:
            connector_name = "imported-api"
    
    # Determine version
    if version_override:
        connector_version = version_override
    else:
        connector_version = info.get('version', '1.0.0')
        # Ensure it's valid semver
        if not re.match(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*).*$', connector_version):
            connector_version = '1.0.0'
    
    # Extract base URL from OpenAPI spec
    base_url = extract_base_url(spec_data, source_url, verbose)
    
    # Extract and convert paths to tools
    tools = []
    paths = spec_data.get('paths', {})
    
    for path, path_item in paths.items():
        # Apply include/exclude filters
        if include_patterns and not any(re.search(pattern, path) for pattern in include_patterns):
            continue
        if exclude_patterns and any(re.search(pattern, path) for pattern in exclude_patterns):
            continue
        
        # Convert each HTTP method to a tool
        for method, operation in path_item.items():
            if method.lower() not in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
                continue
            
            if len(tools) >= max_tools:
                if verbose:
                    click.echo(f"  Reached maximum tools limit ({max_tools}), stopping conversion")
                break
            
            tool = convert_operation_to_tool(path, method, operation, verbose)
            if tool:
                tools.append(tool)
        
        if len(tools) >= max_tools:
            break
    
    if not tools:
        raise ValueError("No valid tools could be generated from OpenAPI specification")
    
    # Build manifest
    manifest = {
        "connector": {
            "name": connector_name,
            "version": connector_version,
        }
    }
    
    # Add base_url if extracted
    if base_url:
        manifest["connector"]["base_url"] = base_url
        if verbose:
            click.echo(f"  Using base URL: {base_url}")
    
    # Add tools to manifest
    manifest["connector"]["tools"] = tools
    
    return manifest


def convert_operation_to_tool(path: str, method: str, operation: Dict[str, Any], verbose: bool) -> Optional[Dict[str, Any]]:
    """
    Convert a single OpenAPI operation to MCP tool definition.
    
    Args:
        path: API path (e.g., "/users/{id}")
        method: HTTP method (e.g., "get")
        operation: OpenAPI operation object
        verbose: Whether to show verbose output
        
    Returns:
        MCP tool dictionary or None if conversion fails
    """
    try:
        # Generate tool name
        operation_id = operation.get('operationId')
        if operation_id:
            tool_name = to_snake_case(operation_id)
        else:
            # Generate from path and method
            path_parts = [part for part in path.split('/') if part and not part.startswith('{')]
            tool_name = f"{method.lower()}_{'_'.join(path_parts)}"
        
        # Ensure valid tool name
        tool_name = re.sub(r'[^a-z0-9_]', '_', tool_name.lower())
        tool_name = re.sub(r'_+', '_', tool_name).strip('_')
        if not tool_name or not tool_name[0].isalpha():
            tool_name = f"api_{tool_name}"
        
        # Generate description
        description = operation.get('summary') or operation.get('description') or f"{method.upper()} {path}"
        if len(description) > 1000:
            description = description[:997] + "..."
        
        # Generate endpoint - use the actual API path and method
        # This should include the full path so the runtime knows how to make the actual HTTP request
        endpoint = f"{method.upper()} {path}"
        
        # Build input schema from parameters and request body
        input_schema = build_input_schema(operation)
        
        # Build output schema from responses
        output_schema = build_output_schema(operation)
        
        tool = {
            "name": tool_name,
            "description": description,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "endpoint": endpoint,
            "auth": {"type": "none"}  # Phase 0-2 only supports 'none'
        }
        
        if verbose:
            click.echo(f"    Generated tool: {tool_name} -> {endpoint}")
        
        return tool
        
    except Exception as e:
        if verbose:
            click.echo(f"    Failed to convert {method.upper()} {path}: {e}")
        return None


def build_input_schema(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Build JSON Schema for tool input from OpenAPI operation parameters and request body."""
    schema = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    # Add parameters (query, path, header)
    parameters = operation.get('parameters', [])
    for param in parameters:
        param_name = param.get('name')
        
        # Handle both OpenAPI 3.x (schema property) and Swagger 2.0 (direct type property)
        if 'schema' in param:
            # OpenAPI 3.x format
            param_schema = param['schema']
        else:
            # Swagger 2.0 format - build schema from type/format properties
            param_type = param.get('type', 'string')
            # Handle special Swagger 2.0 type 'file' -> convert to 'string' for JSON Schema
            if param_type == 'file':
                param_type = 'string'
            
            param_schema = {"type": param_type}
            if 'format' in param:
                param_schema['format'] = param['format']
            if 'enum' in param:
                param_schema['enum'] = param['enum']
            if 'minimum' in param:
                param_schema['minimum'] = param['minimum']
            if 'maximum' in param:
                param_schema['maximum'] = param['maximum']
            if 'items' in param:
                param_schema['items'] = param['items']
        
        if param_name:
            schema["properties"][param_name] = {
                **param_schema,
                "description": param.get('description', f"Parameter: {param_name}")
            }
            
            if param.get('required', False):
                schema["required"].append(param_name)
    
    # Add request body if present
    request_body = operation.get('requestBody')
    if request_body:
        content = request_body.get('content', {})
        # Look for JSON content
        json_content = content.get('application/json') or content.get('application/*') or next(iter(content.values()), {})
        body_schema = json_content.get('schema', {"type": "object"})
        
        # If body schema has properties, merge them
        if body_schema.get('type') == 'object' and 'properties' in body_schema:
            for prop_name, prop_schema in body_schema['properties'].items():
                schema["properties"][prop_name] = prop_schema
            
            # Add required fields from body
            body_required = body_schema.get('required', [])
            schema["required"].extend(body_required)
        else:
            # Add entire body as 'body' parameter
            schema["properties"]["body"] = body_schema
            if request_body.get('required', False):
                schema["required"].append("body")
    
    return schema


def build_output_schema(operation: Dict[str, Any]) -> Dict[str, Any]:
    """Build JSON Schema for tool output from OpenAPI operation responses."""
    responses = operation.get('responses', {})
    
    # Look for successful response (200, 201, etc.)
    success_response = None
    for status_code, response in responses.items():
        if isinstance(status_code, str) and status_code.startswith('2'):
            success_response = response
            break
    
    if not success_response:
        # Use default response or first available
        success_response = responses.get('default', next(iter(responses.values()), {}))
    
    # Extract schema from response content
    content = success_response.get('content', {})
    if content:
        # Look for JSON content
        json_content = content.get('application/json') or content.get('application/*') or next(iter(content.values()), {})
        return json_content.get('schema', {"type": "object", "properties": {"result": {"type": "string"}}})
    
    # Default output schema
    return {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "Operation result"
            }
        },
        "required": ["result"]
    }


def to_snake_case(text: str) -> str:
    """Convert string to snake_case."""
    # Handle camelCase and PascalCase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()