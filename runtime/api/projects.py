"""
Project management endpoints for the MCP Runtime Orchestrator.

This module handles project-related operations including project
configuration, connector management, and runtime instances.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
import yaml
import os
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.config import Settings, get_settings
from models.manifest import ConnectorManifest
from core.registry_service import get_registry_service

router = APIRouter()
logger = logging.getLogger(__name__)


class ProjectConnector(BaseModel):
    """Project connector configuration."""
    connector_id: str
    version: str
    enabled: bool = True
    config: Dict[str, Any] = {}


class Project(BaseModel):
    """Project model."""
    id: str
    name: str
    description: Optional[str] = None
    tenant_id: str
    connectors: List[ProjectConnector] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    """Request model for creating a project."""
    name: str
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    """Request model for updating a project."""
    name: Optional[str] = None
    description: Optional[str] = None


class MCPToolParameter(BaseModel):
    """MCP tool parameter definition."""
    name: str
    type: str
    description: str
    required: bool = True


class MCPTool(BaseModel):
    """MCP tool definition for manifest response."""
    name: str
    description: str
    parameters: List[MCPToolParameter]


class MCPToolManifestResponse(BaseModel):
    """Response model for MCP tool manifest."""
    tools: List[MCPTool]
    project_id: str
    connector_count: int
    total_tools: int


class ProjectResponse(BaseModel):
    """Response model for project operations."""
    project: Project


class ProjectListResponse(BaseModel):
    """Response model for listing projects."""
    projects: List[Project]
    total: int
    page: int
    page_size: int


class ToolInvokeRequest(BaseModel):
    """Request model for tool invocation."""
    tool_name: str
    parameters: Dict[str, Any] = {}
    timeout_seconds: Optional[int] = 30


class ToolInvokeResponse(BaseModel):
    """Response model for tool invocation."""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int
    tool_name: str
    connector_id: Optional[str] = None
    invocation_id: str


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    settings: Settings = Depends(get_settings)
):
    """
    List projects for the current tenant.
    
    Returns a paginated list of projects accessible to the current tenant.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Projects list requested",
        extra={
            "tenant_id": tenant_id,
            "page": page,
            "page_size": page_size,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual database query with tenant filtering
    # For now, return placeholder data
    projects = [
        Project(
            id="project-1",
            name="Sample Project",
            description="A sample project for testing",
            tenant_id=tenant_id or "default-tenant",
            connectors=[
                ProjectConnector(
                    connector_id="weather-api",
                    version="1.0.0",
                    enabled=True
                )
            ]
        )
    ]
    
    return ProjectListResponse(
        projects=projects,
        total=len(projects),
        page=page,
        page_size=page_size
    )


@router.post("/", response_model=ProjectResponse)
async def create_project(
    request: Request,
    project_request: ProjectCreateRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Create a new project.
    
    Creates a new project for the current tenant with the specified
    name and description.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Project creation requested",
        extra={
            "tenant_id": tenant_id,
            "project_name": project_request.name,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual project creation in database
    # For now, return placeholder response
    import uuid
    project = Project(
        id=str(uuid.uuid4()),
        name=project_request.name,
        description=project_request.description,
        tenant_id=tenant_id or "default-tenant",
        connectors=[]
    )
    
    return ProjectResponse(project=project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Get a specific project by ID.
    
    Returns the project details if it exists and belongs to the current tenant.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Project details requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual database query with tenant filtering
    # For now, return placeholder data or 404
    if project_id != "project-1":
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = Project(
        id=project_id,
        name="Sample Project",
        description="A sample project for testing",
        tenant_id=tenant_id or "default-tenant",
        connectors=[
            ProjectConnector(
                connector_id="weather-api",
                version="1.0.0",
                enabled=True
            )
        ]
    )
    
    return ProjectResponse(project=project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    request: Request,
    project_id: str,
    project_request: ProjectUpdateRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Update a project.
    
    Updates the specified project with new name and/or description.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Project update requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual project update in database
    # For now, return placeholder response
    if project_id != "project-1":
        raise HTTPException(status_code=404, detail="Project not found")
    
    project = Project(
        id=project_id,
        name=project_request.name or "Sample Project",
        description=project_request.description,
        tenant_id=tenant_id or "default-tenant",
        connectors=[]
    )
    
    return ProjectResponse(project=project)


def _load_connector_manifest(connector_id: str, settings: Settings) -> Optional[ConnectorManifest]:
    """
    Load connector manifest from samples directory.
    
    In P0-1 phase, we load from local samples. In future phases,
    this will connect to the Registry API to fetch connector manifests.
    """
    try:
        samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")
        manifest_path = os.path.join(samples_dir, f"{connector_id}.yaml")
        
        if not os.path.exists(manifest_path):
            logger.warning(f"Connector manifest not found: {manifest_path}")
            return None
            
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = yaml.safe_load(f)
            
        return ConnectorManifest.from_yaml_dict(manifest_data)
        
    except Exception as e:
        logger.error(
            f"Failed to load connector manifest for {connector_id}",
            exc_info=True,
            extra={"connector_id": connector_id, "error": str(e)}
        )
        return None


def _convert_json_schema_to_mcp_parameters(schema: Dict[str, Any]) -> List[MCPToolParameter]:
    """
    Convert JSON Schema to MCP tool parameters.
    
    Extracts parameters from a JSON Schema object and converts them
    to MCP tool parameter format.
    """
    parameters: List[MCPToolParameter] = []
    
    if schema.get("type") != "object":
        return parameters
        
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    
    for param_name, param_schema in properties.items():
        param_type = param_schema.get("type", "string")
        description = param_schema.get("description", "")
        is_required = param_name in required_fields
        
        parameters.append(MCPToolParameter(
            name=param_name,
            type=param_type,
            description=description,
            required=is_required
        ))
    
    return parameters


@router.get("/{project_id}/runtime/manifest", response_model=MCPToolManifestResponse)
async def get_project_runtime_manifest(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Get merged MCP-compatible tool manifest for enabled connectors.
    
    Returns a unified tool manifest containing all tools from enabled
    connectors for the specified project, formatted for MCP compatibility.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Project runtime manifest requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual database query to get project and connectors
    # For now, simulate a project with enabled connectors
    if project_id != "project-1":
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Simulate enabled connectors for the project
    enabled_connectors = [
        ProjectConnector(
            connector_id="weather-api",
            version="1.0.0",
            enabled=True
        ),
        ProjectConnector(
            connector_id="calculator",
            version="0.1.0",
            enabled=True
        ),
        ProjectConnector(
            connector_id="task-manager",
            version="1.2.0",
            enabled=False  # This should be excluded from manifest
        )
    ]
    
    mcp_tools: List[MCPTool] = []
    connector_count = 0
    
    for connector in enabled_connectors:
        if not connector.enabled:
            continue
            
        # Load connector manifest
        manifest = _load_connector_manifest(connector.connector_id, settings)
        if not manifest:
            logger.warning(
                f"Skipping connector {connector.connector_id}: manifest not found"
            )
            continue
            
        connector_count += 1
        
        # Convert each tool to MCP format
        for tool in manifest.tools:
            # Convert JSON Schema input parameters to MCP format
            parameters = _convert_json_schema_to_mcp_parameters(tool.input_schema)
            
            # Create MCP tool with connector prefix to avoid naming conflicts
            mcp_tool_name = f"{connector.connector_id}.{tool.name}"
            
            mcp_tool = MCPTool(
                name=mcp_tool_name,
                description=f"[{manifest.name}] {tool.description}",
                parameters=parameters
            )
            
            mcp_tools.append(mcp_tool)
    
    logger.info(
        "Project runtime manifest generated",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "connector_count": connector_count,
            "total_tools": len(mcp_tools),
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    return MCPToolManifestResponse(
        tools=mcp_tools,
        project_id=project_id,
        connector_count=connector_count,
        total_tools=len(mcp_tools)
    )


@router.delete("/{project_id}")
async def delete_project(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Delete a project.
    
    Deletes the specified project and all its associated resources.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Project deletion requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual project deletion from database
    # For now, return success
    if project_id != "project-1":
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {"message": "Project deleted successfully"}


def _parse_tool_name(tool_name: str) -> tuple[str, str]:
    """
    Parse tool name to extract connector_id and tool_name.
    
    Expected format: "connector_id.tool_name"
    Returns tuple of (connector_id, tool_name)
    """
    if "." not in tool_name:
        raise ValueError(f"Invalid tool name format. Expected 'connector_id.tool_name', got '{tool_name}'")
    
    parts = tool_name.split(".", 1)
    return parts[0], parts[1]


async def _simulate_tool_execution(
    connector_id: str,
    tool_name: str, 
    parameters: Dict[str, Any],
    settings: Settings
) -> Dict[str, Any]:
    """
    Simulate tool execution for P0-1 phase.
    
    In future phases, this will:
    1. Load the actual connector runtime
    2. Validate parameters against the tool schema
    3. Execute the tool with proper auth, retries, rate limiting
    4. Return structured results
    
    For now, we simulate based on connector samples.
    """
    # Load connector manifest to validate tool exists
    manifest = _load_connector_manifest(connector_id, settings)
    if not manifest:
        raise HTTPException(
            status_code=404, 
            detail=f"Connector '{connector_id}' not found"
        )
    
    # Find the requested tool
    tool_definition = None
    for tool in manifest.tools:
        if tool.name == tool_name:
            tool_definition = tool
            break
    
    if not tool_definition:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found in connector '{connector_id}'"
        )
    
    # Simulate execution delay
    await asyncio.sleep(0.1)
    
    # Return simulated results based on connector type
    if connector_id == "weather-api":
        if tool_name == "get_current_weather":
            location = parameters.get("location", "Unknown")
            return {
                "location": location,
                "temperature": 22.5,
                "condition": "Partly cloudy",
                "humidity": 65,
                "wind_speed": 12.3,
                "timestamp": datetime.now().isoformat()
            }
        elif tool_name == "get_forecast":
            location = parameters.get("location", "Unknown")
            days = parameters.get("days", 3)
            return {
                "location": location,
                "forecast": [
                    {
                        "date": "2025-08-05",
                        "high": 25,
                        "low": 18,
                        "condition": "Sunny"
                    },
                    {
                        "date": "2025-08-06", 
                        "high": 23,
                        "low": 16,
                        "condition": "Cloudy"
                    },
                    {
                        "date": "2025-08-07",
                        "high": 26,
                        "low": 19,
                        "condition": "Partly cloudy"
                    }
                ][:days]
            }
    elif connector_id == "calculator":
        if tool_name == "add":
            a = parameters.get("a", 0)
            b = parameters.get("b", 0)
            return {"result": a + b}
        elif tool_name == "subtract":
            a = parameters.get("a", 0)
            b = parameters.get("b", 0)
            return {"result": a - b}
        elif tool_name == "multiply":
            a = parameters.get("a", 0)
            b = parameters.get("b", 0)
            return {"result": a * b}
        elif tool_name == "divide":
            a = parameters.get("a", 0)
            b = parameters.get("b", 1)
            if b == 0:
                raise HTTPException(status_code=400, detail="Division by zero")
            return {"result": a / b}
    elif connector_id == "task-manager":
        if tool_name == "create_task":
            title = parameters.get("title", "Untitled Task")
            return {
                "task_id": "task-12345",
                "title": title,
                "description": parameters.get("description", ""),
                "status": "open",
                "created_at": datetime.now().isoformat()
            }
        elif tool_name == "list_tasks":
            return {
                "tasks": [
                    {
                        "task_id": "task-12345",
                        "title": "Sample Task",
                        "status": "open",
                        "created_at": "2025-08-04T10:00:00Z"
                    }
                ],
                "total": 1
            }
    
    # Default fallback
    return {
        "message": f"Tool '{tool_name}' executed successfully",
        "parameters": parameters,
        "connector": connector_id
    }


@router.post("/{project_id}/runtime/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(
    request: Request,
    project_id: str,
    invoke_request: ToolInvokeRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Invoke a tool from an enabled connector within the project runtime.
    
    This endpoint provides generic tool invocation capabilities for the MCP platform.
    Tools are identified by their fully qualified name (connector_id.tool_name) and
    executed with the provided parameters.
    
    In P0-1 phase, this simulates tool execution. In future phases, this will:
    - Load actual connector runtimes
    - Apply authentication and authorization
    - Implement rate limiting and retry logic
    - Provide real-time execution monitoring
    - Support streaming responses for long-running operations
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    correlation_id = getattr(request.state, "correlation_id", None)
    invocation_id = f"inv-{uuid4().hex[:8]}"
    
    start_time = datetime.now()
    connector_id = None  # Initialize for error handling
    
    logger.info(
        "Tool invocation requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "tool_name": invoke_request.tool_name,
            "invocation_id": invocation_id,
            "correlation_id": correlation_id
        }
    )
    
    try:
        # Validate project exists and belongs to tenant
        # TODO: Implement actual database query
        if project_id != "project-1":
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Parse tool name to extract connector and tool
        try:
            connector_id, tool_name = _parse_tool_name(invoke_request.tool_name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Check if connector is enabled for this project
        # TODO: Implement actual database query for project connectors
        # For now, simulate enabled connectors
        enabled_connectors = {"weather-api", "calculator"}
        if connector_id not in enabled_connectors:
            raise HTTPException(
                status_code=403, 
                detail=f"Connector '{connector_id}' is not enabled for this project"
            )
        
        # Execute the tool
        result = await _simulate_tool_execution(
            connector_id=connector_id,
            tool_name=tool_name,
            parameters=invoke_request.parameters,
            settings=settings
        )
        
        execution_time = datetime.now() - start_time
        execution_time_ms = int(execution_time.total_seconds() * 1000)
        
        logger.info(
            "Tool invocation completed successfully",
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "tool_name": invoke_request.tool_name,
                "connector_id": connector_id,
                "invocation_id": invocation_id,
                "execution_time_ms": execution_time_ms,
                "correlation_id": correlation_id
            }
        )
        
        return ToolInvokeResponse(
            success=True,
            result=result,
            execution_time_ms=execution_time_ms,
            tool_name=invoke_request.tool_name,
            connector_id=connector_id,
            invocation_id=invocation_id
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        execution_time = datetime.now() - start_time
        execution_time_ms = int(execution_time.total_seconds() * 1000)
        
        logger.error(
            "Tool invocation failed",
            exc_info=True,
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "tool_name": invoke_request.tool_name,
                "invocation_id": invocation_id,
                "execution_time_ms": execution_time_ms,
                "error": str(e),
                "correlation_id": correlation_id
            }
        )
        
        return ToolInvokeResponse(
            success=False,
            error=f"Tool execution failed: {str(e)}",
            execution_time_ms=execution_time_ms,
            tool_name=invoke_request.tool_name,
            connector_id=connector_id,
            invocation_id=invocation_id
        )


# Registry-integrated endpoints

class ConnectorInstallRequest(BaseModel):
    """Request model for installing a connector."""
    connector_name: str
    version: Optional[str] = None
    enabled: bool = True
    config: Dict[str, Any] = {}


class ConnectorManifestRequest(BaseModel):
    """Request model for installing a connector from manifest."""
    manifest: Dict[str, Any]
    enabled: bool = True
    config: Dict[str, Any] = {}


@router.post("/{project_id}/connectors/install-from-file")
async def install_connector_from_file(
    request: Request,
    project_id: str,
    file_path: str,
    enabled: bool = True,
    settings: Settings = Depends(get_settings)
):
    """
    Install a connector from a descriptor file.
    
    This endpoint allows installing a connector by providing the path
    to its YAML descriptor file. Supports hot-reload if enabled.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing tenant ID")
    
    registry_service = get_registry_service()
    
    try:
        from pathlib import Path
        
        connector = registry_service.install_connector_from_file(
            project_id=project_id,
            tenant_id=tenant_id,
            file_path=Path(file_path),
            enabled=enabled
        )
        
        return {
            "success": True,
            "connector": {
                "name": connector.name,
                "version": connector.version,
                "enabled": connector.enabled,
                "tool_count": len(connector.tools),
                "loaded_at": connector.loaded_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.exception("Failed to install connector from file")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to install connector: {str(e)}"
        )


@router.post("/{project_id}/connectors/install-from-manifest")
async def install_connector_from_manifest(
    request: Request,
    project_id: str,
    manifest_request: ConnectorManifestRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Install a connector from a manifest object.
    
    This endpoint allows installing a connector by providing its
    manifest definition directly in the request body.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing tenant ID")
    
    registry_service = get_registry_service()
    
    try:
        # Create manifest from request data
        manifest = ConnectorManifest.from_yaml_dict(manifest_request.manifest)
        
        connector = registry_service.install_connector_from_manifest(
            project_id=project_id,
            tenant_id=tenant_id,
            manifest=manifest,
            config=manifest_request.config,
            enabled=manifest_request.enabled
        )
        
        return {
            "success": True,
            "connector": {
                "name": connector.name,
                "version": connector.version,
                "enabled": connector.enabled,
                "tool_count": len(connector.tools),
                "loaded_at": connector.loaded_at.isoformat()
            }
        }
        
    except Exception as e:
        logger.exception("Failed to install connector from manifest")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to install connector: {str(e)}"
        )


@router.delete("/{project_id}/connectors/{connector_name}")
async def uninstall_connector(
    request: Request,
    project_id: str,
    connector_name: str,
    settings: Settings = Depends(get_settings)
):
    """
    Uninstall a connector from a project.
    """
    registry_service = get_registry_service()
    
    success = registry_service.uninstall_connector(project_id, connector_name)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_name}' not found in project '{project_id}'"
        )
    
    return {"success": True, "message": f"Connector '{connector_name}' uninstalled"}


@router.post("/{project_id}/connectors/{connector_name}/enable")
async def enable_connector(
    request: Request,
    project_id: str,
    connector_name: str,
    settings: Settings = Depends(get_settings)
):
    """
    Enable a connector in a project.
    """
    registry_service = get_registry_service()
    
    success = registry_service.enable_connector(project_id, connector_name)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_name}' not found in project '{project_id}'"
        )
    
    return {"success": True, "message": f"Connector '{connector_name}' enabled"}


@router.post("/{project_id}/connectors/{connector_name}/disable")
async def disable_connector(
    request: Request,
    project_id: str,
    connector_name: str,
    settings: Settings = Depends(get_settings)
):
    """
    Disable a connector in a project.
    """
    registry_service = get_registry_service()
    
    success = registry_service.disable_connector(project_id, connector_name)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_name}' not found in project '{project_id}'"
        )
    
    return {"success": True, "message": f"Connector '{connector_name}' disabled"}


@router.get("/{project_id}/connectors")
async def list_project_connectors(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    List all connectors installed in a project.
    """
    registry_service = get_registry_service()
    
    connectors = registry_service.get_project_connectors(project_id)
    
    return {
        "project_id": project_id,
        "connectors": connectors,
        "total": len(connectors)
    }


@router.get("/{project_id}/tools")
async def list_project_tools(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    List all available tools in a project.
    """
    registry_service = get_registry_service()
    
    tools = registry_service.get_project_tools(project_id)
    
    return {
        "project_id": project_id,
        "tools": tools,
        "total": len(tools)
    }


@router.get("/{project_id}/tools/{tool_name}")
async def get_tool_definition(
    request: Request,
    project_id: str,
    tool_name: str,
    settings: Settings = Depends(get_settings)
):
    """
    Get the definition of a specific tool.
    """
    registry_service = get_registry_service()
    
    tool = registry_service.get_tool_definition(project_id, tool_name)
    
    if not tool:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found in project '{project_id}'"
        )
    
    return tool


@router.get("/{project_id}/stats")
async def get_project_stats(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Get statistics for a project registry.
    """
    registry_service = get_registry_service()
    
    stats = registry_service.get_project_stats(project_id)
    
    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found"
        )
    
    return stats


@router.post("/{project_id}/hot-reload")
async def perform_hot_reload(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Check for file changes and perform hot-reload of updated connectors.
    """
    if not settings.HOT_RELOAD:
        raise HTTPException(
            status_code=400,
            detail="Hot reload is disabled"
        )
    
    registry_service = get_registry_service()
    
    reloaded_connectors = await registry_service.perform_hot_reload_check(project_id)
    
    return {
        "project_id": project_id,
        "reloaded_connectors": reloaded_connectors,
        "count": len(reloaded_connectors)
    }


@router.post("/{project_id}/install-samples")
async def install_sample_connectors(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Install sample connectors for demonstration purposes.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing tenant ID")
    
    registry_service = get_registry_service()
    
    # Ensure project registry exists
    registry_service.ensure_project_registry(project_id, tenant_id)
    
    installed_connectors = registry_service.install_sample_connectors(project_id, tenant_id)
    
    return {
        "project_id": project_id,
        "installed_connectors": installed_connectors,
        "count": len(installed_connectors)
    }
