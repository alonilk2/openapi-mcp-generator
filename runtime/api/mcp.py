"""
MCP protocol endpoints for the MCP Runtime Orchestrator.

This module handles MCP (Model Context Protocol) specific endpoints
for tool discovery, execution, and protocol compliance.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.exceptions import ConnectorNotFoundError, ToolExecutionError
from core.builtin_tools import builtin_tool_handler
from core.registry import get_registry
from core.registry_service import get_registry_service

router = APIRouter()
logger = logging.getLogger(__name__)


class MCPToolParameter(BaseModel):
    """MCP tool parameter definition."""
    name: str
    type: str
    description: str
    required: bool = True


class MCPTool(BaseModel):
    """MCP tool definition."""
    name: str
    description: str
    parameters: List[MCPToolParameter]


class MCPToolsResponse(BaseModel):
    """Response for MCP tools listing."""
    tools: List[MCPTool]


class MCPToolExecutionRequest(BaseModel):
    """Request for MCP tool execution."""
    name: str
    arguments: Dict[str, Any]


class MCPToolExecutionResponse(BaseModel):
    """Response for MCP tool execution."""
    content: List[Dict[str, Any]]
    isError: bool = False


class MCPCapabilitiesResponse(BaseModel):
    """MCP server capabilities response."""
    capabilities: Dict[str, Any]
    serverInfo: Dict[str, str]


@router.get("/capabilities", response_model=MCPCapabilitiesResponse)
async def get_capabilities(
    request: Request,
    settings: Settings = Depends(get_settings)
):
    """
    Get MCP server capabilities.
    
    Returns the capabilities supported by this MCP server instance,
    including available tools and protocol features.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "MCP capabilities requested",
        extra={
            "tenant_id": tenant_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    capabilities = {
        "tools": {
            "listChanged": True,
            "supportsProgress": False
        },
        "resources": {
            "subscribe": False,
            "listChanged": False
        },
        "prompts": {
            "listChanged": False
        },
        "experimental": {}
    }
    
    server_info = {
        "name": "MCP Runtime Orchestrator",
        "version": settings.VERSION
    }
    
    return MCPCapabilitiesResponse(
        capabilities=capabilities,
        serverInfo=server_info
    )


@router.get("/tools", response_model=MCPToolsResponse)
async def list_tools(
    request: Request,
    connector_id: str | None = None,
    project_id: str = "default",
    settings: Settings = Depends(get_settings)
):
    """
    List available MCP tools.
    
    Returns all tools available to the current tenant, optionally
    filtered by connector ID. Includes both built-in tools and
    connector-provided tools.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "MCP tools list requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "connector_id": connector_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    all_tools = []

    # Optionally perform hot-reload before listing tools
    try:
        if settings.HOT_RELOAD:
            registry = get_registry()
            updated = registry.check_for_updates(project_id)
            if updated:
                logger.info(
                    "Hot-reload: updating connectors before listing tools",
                    extra={
                        "project_id": project_id,
                        "updated_connectors": updated,
                        "correlation_id": getattr(request.state, "correlation_id", None)
                    }
                )
                for conn_name in updated:
                    try:
                        # hot_reload_connector is async
                        await registry.hot_reload_connector(project_id, conn_name)
                    except Exception as e:
                        logger.warning(
                            "Hot-reload failed for connector",
                            extra={
                                "project_id": project_id,
                                "connector_name": conn_name,
                                "error": str(e),
                                "correlation_id": getattr(request.state, "correlation_id", None)
                            }
                        )
    except Exception as e:
        logger.warning(
            "Hot-reload pre-check failed; continuing without reload",
            extra={
                "project_id": project_id,
                "error": str(e),
                "correlation_id": getattr(request.state, "correlation_id", None)
            }
        )

    # In development, rescan samples to pick up any newly-added manifests
    try:
        if settings.is_development():
            svc = get_registry_service()
            # Ensure default registry exists
            svc.ensure_project_registry(project_id, tenant_id or "default-tenant")
            installed = svc.install_sample_connectors(project_id, tenant_id or "default-tenant")
            if installed:
                logger.info(
                    "Installed/updated sample connectors before listing tools",
                    extra={
                        "project_id": project_id,
                        "installed": installed,
                        "correlation_id": getattr(request.state, "correlation_id", None)
                    }
                )
    except Exception as e:
        logger.warning(
            "Sample rescan failed; continuing without it",
            extra={
                "project_id": project_id,
                "error": str(e),
                "correlation_id": getattr(request.state, "correlation_id", None)
            }
        )

    # Get built-in tools
    for tool in builtin_tool_handler.list_tools():
        mcp_params = []
        for param in tool.parameters:
            mcp_params.append(MCPToolParameter(
                name=param.name,
                type=param.type,
                description=param.description,
                required=param.required
            ))
        
        all_tools.append(MCPTool(
            name=tool.name,
            description=tool.description,
            parameters=mcp_params
        ))
    
    # Get connector-provided tools
    registry = get_registry()
    project_registry = registry.get_project_registry(project_id)
    
    connector_tools_count = 0
    if project_registry:
        # Filter by connector if specified
        if connector_id:
            connector = project_registry.get_connector(connector_id)
            connectors_to_check = {connector_id: connector} if connector else {}
        else:
            connectors_to_check = project_registry.list_connectors()
        
        # Add tools from each connector
        for connector_name, connector in connectors_to_check.items():
            if not connector or not connector.enabled:
                continue
                
            for tool_name, loaded_tool in connector.get_enabled_tools().items():
                tool_def = loaded_tool.definition
                
                # Convert JSON schema properties to MCP tool parameters
                mcp_params = []
                if hasattr(tool_def.input_schema, 'get') and 'properties' in tool_def.input_schema:
                    required_fields = tool_def.input_schema.get('required', [])
                    for param_name, param_schema in tool_def.input_schema['properties'].items():
                        param_type = param_schema.get('type', 'string')
                        param_desc = param_schema.get('description', f'Parameter {param_name}')
                        is_required = param_name in required_fields
                        
                        mcp_params.append(MCPToolParameter(
                            name=param_name,
                            type=param_type,
                            description=param_desc,
                            required=is_required
                        ))
                
                all_tools.append(MCPTool(
                    name=tool_name,
                    description=tool_def.description,
                    parameters=mcp_params
                ))
                connector_tools_count += 1
    
    logger.info(
        "MCP tools list response prepared",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "builtin_tools_count": len(builtin_tool_handler.list_tools()),
            "connector_tools_count": connector_tools_count,
            "total_tools_count": len(all_tools),
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    return MCPToolsResponse(tools=all_tools)


@router.post("/tools/call", response_model=MCPToolExecutionResponse)
async def call_tool(
    request: Request,
    execution_request: MCPToolExecutionRequest,
    project_id: str = "default"
):
    """
    Execute an MCP tool.
    
    Calls the specified tool with the provided arguments and returns
    the result in MCP format. Supports both built-in tools and
    connector-provided tools.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    correlation_id = getattr(request.state, "correlation_id", None)
    
    logger.info(
        "MCP tool execution requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "tool_name": execution_request.name,
            "correlation_id": correlation_id
        }
    )
    
    try:
        # Check if this is a built-in tool first
        if builtin_tool_handler.has_tool(execution_request.name):
            result = await builtin_tool_handler.execute_tool(
                execution_request.name,
                execution_request.arguments
            )
            
            logger.info(
                "Built-in tool execution completed",
                extra={
                    "tenant_id": tenant_id,
                    "tool_name": execution_request.name,
                    "execution_time_ms": result.execution_time_ms,
                    "is_error": result.is_error,
                    "correlation_id": correlation_id
                }
            )
            
            return MCPToolExecutionResponse(
                content=result.content,
                isError=result.is_error
            )
        
        # Check for connector tools
        registry = get_registry()
        project_registry = registry.get_project_registry(project_id)
        
        if project_registry:
            loaded_tool = project_registry.get_tool(execution_request.name)
            if loaded_tool:
                # Mark tool as used for statistics
                loaded_tool.mark_used()
                
                # Always execute via the ToolExecutionClient (auth or none)
                from ..core.authenticated_client import get_tool_execution_client
                from ..core.credential_resolver import CredentialResolutionError

                try:
                    execution_client = get_tool_execution_client()

                    result_data = await execution_client.execute_tool(
                        tool=loaded_tool.definition,
                        connector_name=loaded_tool.connector_name,
                        input_data=execution_request.arguments,
                        base_url=None
                    )

                    logger.info(
                        "Connector tool execution completed",
                        extra={
                            "tenant_id": tenant_id,
                            "project_id": project_id,
                            "tool_name": execution_request.name,
                            "connector_name": loaded_tool.connector_name,
                            "connector_version": loaded_tool.connector_version,
                            "correlation_id": correlation_id,
                            "auth_type": loaded_tool.definition.auth_type
                        }
                    )

                    return MCPToolExecutionResponse(
                        content=[{
                            "type": "text",
                            "text": f"Tool '{execution_request.name}' executed successfully",
                            "result": result_data,
                            "connector": loaded_tool.connector_name,
                            "version": loaded_tool.connector_version,
                            "auth_type": loaded_tool.definition.auth_type
                        }],
                        isError=False
                    )

                except CredentialResolutionError as e:
                    logger.error(
                        "Credential resolution failed for connector tool",
                        extra={
                            "tenant_id": tenant_id,
                            "project_id": project_id,
                            "tool_name": execution_request.name,
                            "connector_name": loaded_tool.connector_name,
                            "error": str(e),
                            "correlation_id": correlation_id
                        }
                    )

                    return MCPToolExecutionResponse(
                        content=[{
                            "type": "text",
                            "text": f"Authentication failed for tool '{execution_request.name}': {str(e)}",
                            "error_type": "credential_resolution_error",
                            "connector_name": loaded_tool.connector_name,
                            "correlation_id": correlation_id
                        }],
                        isError=True
                    )

                except Exception as e:
                    logger.error(
                        "Tool execution failed",
                        extra={
                            "tenant_id": tenant_id,
                            "project_id": project_id,
                            "tool_name": execution_request.name,
                            "connector_name": loaded_tool.connector_name,
                            "error": str(e),
                            "correlation_id": correlation_id
                        }
                    )

                    return MCPToolExecutionResponse(
                        content=[{
                            "type": "text",
                            "text": f"Tool execution failed: {str(e)}",
                            "error_type": "execution_error",
                            "connector_name": loaded_tool.connector_name,
                            "correlation_id": correlation_id
                        }],
                        isError=True
                    )
        
        # Tool not found
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{execution_request.name}' not found"
        )
        
    except Exception as e:
        logger.error(
            "MCP tool execution failed",
            exc_info=True,
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "tool_name": execution_request.name,
                "error": str(e),
                "correlation_id": correlation_id
            }
        )
        
        # Return error in MCP format
        content = [{"type": "text", "text": f"Error: {str(e)}"}]
        return MCPToolExecutionResponse(content=content, isError=True)


# Note: mock execution path removed for P0; all connector tools execute via ToolExecutionClient.
