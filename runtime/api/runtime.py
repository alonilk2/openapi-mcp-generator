"""
Runtime management endpoints for the MCP Runtime Orchestrator.

This module handles runtime operations including connector loading,
execution monitoring, and WebSocket streaming for development.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.registry import get_registry

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectorStatus(BaseModel):
    """Connector runtime status."""
    connector_id: str
    version: str
    status: str  # "loading", "ready", "error", "stopped"
    last_updated: Optional[str] = None
    error_message: Optional[str] = None
    tool_count: int = 0


class RuntimeStatus(BaseModel):
    """Runtime status response."""
    project_id: str
    status: str  # "starting", "running", "stopping", "stopped", "error"
    connectors: List[ConnectorStatus] = []
    uptime_seconds: Optional[float] = None
    last_updated: Optional[str] = None


class RuntimeStartRequest(BaseModel):
    """Request to start a runtime instance."""
    project_id: str
    hot_reload: bool = False


class RuntimeLogEntry(BaseModel):
    """Runtime log entry."""
    timestamp: str
    level: str
    message: str
    connector_id: Optional[str] = None
    tool_name: Optional[str] = None
    correlation_id: Optional[str] = None


@router.post("/start")
async def start_runtime(
    request: Request,
    start_request: RuntimeStartRequest,
    settings: Settings = Depends(get_settings)
):
    """
    Start a runtime instance for a project.
    
    Loads all enabled connectors for the project and starts the
    runtime environment.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Runtime start requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": start_request.project_id,
            "hot_reload": start_request.hot_reload,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual runtime startup
    # - Load project configuration
    # - Download and validate connectors
    # - Initialize connector instances
    # - Start monitoring
    
    return {
        "message": "Runtime start initiated",
        "project_id": start_request.project_id,
        "status": "starting"
    }


@router.post("/stop/{project_id}")
async def stop_runtime(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Stop a runtime instance.
    
    Gracefully shuts down all connectors and cleans up resources.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Runtime stop requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual runtime shutdown
    # - Stop all connector instances
    # - Clean up resources
    # - Update status
    
    return {
        "message": "Runtime stop initiated",
        "project_id": project_id,
        "status": "stopping"
    }


@router.get("/status/{project_id}", response_model=RuntimeStatus)
async def get_runtime_status(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Get runtime status for a project.
    
    Returns the current status of the runtime and all loaded connectors.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Runtime status requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual status retrieval
    # For now, return placeholder data
    status = RuntimeStatus(
        project_id=project_id,
        status="running",
        connectors=[
            ConnectorStatus(
                connector_id="weather-api",
                version="1.0.0",
                status="ready",
                tool_count=3
            )
        ],
        uptime_seconds=3600.0
    )
    
    return status


@router.get("/logs/{project_id}")
async def get_runtime_logs(
    request: Request,
    project_id: str,
    limit: int = 100,
    connector_id: Optional[str] = None,
    settings: Settings = Depends(get_settings)
):
    """
    Get runtime logs for a project.
    
    Returns recent log entries from the runtime and connectors.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Runtime logs requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "connector_id": connector_id,
            "limit": limit,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    # TODO: Implement actual log retrieval
    # For now, return placeholder data
    logs = [
        RuntimeLogEntry(
            timestamp="2024-01-01T00:00:00Z",
            level="INFO",
            message="Runtime started successfully",
            connector_id=None
        ),
        RuntimeLogEntry(
            timestamp="2024-01-01T00:00:01Z",
            level="INFO",
            message="Connector loaded successfully",
            connector_id="weather-api"
        )
    ]
    
    return {"logs": logs}


@router.websocket("/stream/{project_id}")
async def stream_runtime_logs(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for streaming runtime logs.
    
    Provides real-time log streaming for development and monitoring.
    Used by the Web Console for live log viewing.
    """
    await websocket.accept()
    
    logger.info(
        "Runtime log stream started",
        extra={
            "project_id": project_id,
            "client": websocket.client
        }
    )
    
    try:
        # TODO: Implement actual log streaming
        # - Connect to log aggregation system
        # - Filter by project_id and tenant_id
        # - Stream logs in real-time
        
        # For now, send a welcome message
        await websocket.send_json({
            "type": "log",
            "data": {
                "timestamp": "2024-01-01T00:00:00Z",
                "level": "INFO",
                "message": f"Log stream connected for project {project_id}"
            }
        })
        
        # Keep connection alive
        while True:
            # Wait for client messages (ping/pong, etc.)
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
                
    except Exception as e:
        logger.error(
            "Runtime log stream error",
            exc_info=True,
            extra={
                "project_id": project_id,
                "error": str(e)
            }
        )
    finally:
        logger.info(
            "Runtime log stream ended",
            extra={"project_id": project_id}
        )


@router.post("/reload/{project_id}/check")
async def check_connector_updates(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Check for connector file updates that require hot-reload.
    
    This endpoint checks if any connector manifest files have been
    modified and returns a list of connectors that need reloading.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Hot-reload check requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    if not settings.HOT_RELOAD:
        return {
            "hot_reload_enabled": False,
            "updated_connectors": [],
            "message": "Hot reload is disabled"
        }
    
    try:
        registry = get_registry()
        updated_connectors = registry.check_for_updates(project_id)
        
        return {
            "hot_reload_enabled": True,
            "updated_connectors": updated_connectors,
            "update_count": len(updated_connectors)
        }
        
    except Exception as e:
        logger.error(
            "Hot-reload check failed",
            exc_info=True,
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "error": str(e),
                "correlation_id": getattr(request.state, "correlation_id", None)
            }
        )
        raise HTTPException(status_code=500, detail=f"Hot-reload check failed: {e}")


@router.post("/reload/{project_id}/{connector_name}")
async def hot_reload_connector(
    request: Request,
    project_id: str,
    connector_name: str,
    settings: Settings = Depends(get_settings)
):
    """
    Hot-reload a specific connector.
    
    This endpoint reloads a connector from its manifest file without
    restarting the entire runtime.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Hot-reload requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "connector_name": connector_name,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    if not settings.HOT_RELOAD:
        raise HTTPException(
            status_code=400, 
            detail="Hot reload is disabled"
        )
    
    try:
        registry = get_registry()
        success = await registry.hot_reload_connector(project_id, connector_name)
        
        if success:
            return {
                "success": True,
                "message": f"Connector '{connector_name}' reloaded successfully",
                "connector_name": connector_name,
                "project_id": project_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Connector '{connector_name}' not found or could not be reloaded"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Hot-reload failed",
            exc_info=True,
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "connector_name": connector_name,
                "error": str(e),
                "correlation_id": getattr(request.state, "correlation_id", None)
            }
        )
        raise HTTPException(status_code=500, detail=f"Hot-reload failed: {e}")


@router.post("/reload/{project_id}")
async def hot_reload_all_connectors(
    request: Request,
    project_id: str,
    settings: Settings = Depends(get_settings)
):
    """
    Hot-reload all connectors that have file updates.
    
    This endpoint checks for updates and reloads all connectors that
    have been modified without restarting the runtime.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    
    logger.info(
        "Hot-reload all requested",
        extra={
            "tenant_id": tenant_id,
            "project_id": project_id,
            "correlation_id": getattr(request.state, "correlation_id", None)
        }
    )
    
    if not settings.HOT_RELOAD:
        raise HTTPException(
            status_code=400, 
            detail="Hot reload is disabled"
        )
    
    try:
        registry = get_registry()
        updated_connectors = registry.check_for_updates(project_id)
        
        results = []
        for connector_name in updated_connectors:
            try:
                success = await registry.hot_reload_connector(project_id, connector_name)
                results.append({
                    "connector_name": connector_name,
                    "success": success,
                    "error": None
                })
            except Exception as e:
                results.append({
                    "connector_name": connector_name,
                    "success": False,
                    "error": str(e)
                })
        
        successful_reloads = [r for r in results if r["success"]]
        failed_reloads = [r for r in results if not r["success"]]
        
        return {
            "total_checked": len(updated_connectors),
            "successful_reloads": len(successful_reloads),
            "failed_reloads": len(failed_reloads),
            "results": results,
            "message": f"Reloaded {len(successful_reloads)} of {len(updated_connectors)} connectors"
        }
        
    except Exception as e:
        logger.error(
            "Hot-reload all failed",
            exc_info=True,
            extra={
                "tenant_id": tenant_id,
                "project_id": project_id,
                "error": str(e),
                "correlation_id": getattr(request.state, "correlation_id", None)
            }
        )
        raise HTTPException(status_code=500, detail=f"Hot-reload all failed: {e}")
