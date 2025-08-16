"""
Registry integration utilities and services.

This module provides integration between the internal registry and the
existing project management system, enabling seamless connector management
and tool discovery.
"""

import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from core.registry import get_registry, LoadedConnector, ProjectRegistry
from models.manifest import ConnectorManifest
from core.exceptions import MCPRuntimeException


logger = logging.getLogger(__name__)


class RegistryService:
    """
    Service layer for registry operations.
    
    This class provides high-level operations for managing project registries
    and their connectors, with proper error handling and logging.
    """
    
    def __init__(self):
        self.registry = get_registry()
    
    def ensure_project_registry(self, project_id: str, tenant_id: str) -> ProjectRegistry:
        """
        Ensure a project registry exists, creating it if necessary.
        
        Args:
            project_id: The project ID
            tenant_id: The tenant ID
            
        Returns:
            ProjectRegistry instance
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            registry = self.registry.create_project_registry(project_id, tenant_id)
        return registry
    
    def install_connector_from_file(
        self,
        project_id: str,
        tenant_id: str,
        file_path: Path,
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True
    ) -> LoadedConnector:
        """
        Install a connector from a descriptor file.
        
        Args:
            project_id: The project ID
            tenant_id: The tenant ID
            file_path: Path to the connector descriptor file
            config: Optional configuration override
            enabled: Whether the connector should be enabled
            
        Returns:
            LoadedConnector instance
            
        Raises:
            MCPRuntimeException: If installation fails
        """
        try:
            # Ensure project registry exists
            self.ensure_project_registry(project_id, tenant_id)
            
            # Load connector from file
            connector = self.registry.load_connector_from_file(
                project_id, 
                file_path, 
                config
            )
            connector.enabled = enabled
            
            # Install in registry
            success = self.registry.install_connector(
                project_id, 
                connector, 
                replace_existing=True
            )
            
            if not success:
                raise MCPRuntimeException(
                    message=f"Failed to install connector {connector.name}",
                    error_type="INSTALL_FAILED",
                    status_code=500
                )
            
            logger.info(
                "Connector installed successfully",
                extra={
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "connector_name": connector.name,
                    "connector_version": connector.version,
                    "enabled": enabled,
                    "tool_count": len(connector.tools)
                }
            )
            
            return connector
            
        except MCPRuntimeException:
            raise
        except Exception as e:
            logger.exception("Unexpected error installing connector from file")
            raise MCPRuntimeException(
                message=f"Failed to install connector: {e}",
                error_type="INSTALL_ERROR",
                status_code=500
            )
    
    def install_connector_from_manifest(
        self,
        project_id: str,
        tenant_id: str,
        manifest: ConnectorManifest,
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True
    ) -> LoadedConnector:
        """
        Install a connector from a manifest object.
        
        Args:
            project_id: The project ID
            tenant_id: The tenant ID
            manifest: ConnectorManifest instance
            config: Optional configuration override
            enabled: Whether the connector should be enabled
            
        Returns:
            LoadedConnector instance
            
        Raises:
            MCPRuntimeException: If installation fails
        """
        try:
            # Ensure project registry exists
            self.ensure_project_registry(project_id, tenant_id)
            
            # Load connector from manifest
            connector = self.registry.load_connector_from_manifest(
                project_id, 
                manifest, 
                config
            )
            connector.enabled = enabled
            
            # Install in registry
            success = self.registry.install_connector(
                project_id, 
                connector, 
                replace_existing=True
            )
            
            if not success:
                raise MCPRuntimeException(
                    message=f"Failed to install connector {connector.name}",
                    error_type="INSTALL_FAILED",
                    status_code=500
                )
            
            logger.info(
                "Connector installed successfully from manifest",
                extra={
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "connector_name": connector.name,
                    "connector_version": connector.version,
                    "enabled": enabled,
                    "tool_count": len(connector.tools)
                }
            )
            
            return connector
            
        except MCPRuntimeException:
            raise
        except Exception as e:
            logger.exception("Unexpected error installing connector from manifest")
            raise MCPRuntimeException(
                message=f"Failed to install connector: {e}",
                error_type="INSTALL_ERROR",
                status_code=500
            )
    
    def uninstall_connector(
        self,
        project_id: str,
        connector_name: str
    ) -> bool:
        """
        Uninstall a connector from a project.
        
        Args:
            project_id: The project ID
            connector_name: Name of the connector to uninstall
            
        Returns:
            True if uninstalled, False if not found
        """
        success = self.registry.uninstall_connector(project_id, connector_name)
        
        if success:
            logger.info(
                "Connector uninstalled successfully",
                extra={
                    "project_id": project_id,
                    "connector_name": connector_name
                }
            )
        else:
            logger.warning(
                "Connector not found for uninstall",
                extra={
                    "project_id": project_id,
                    "connector_name": connector_name
                }
            )
        
        return success
    
    def enable_connector(
        self,
        project_id: str,
        connector_name: str
    ) -> bool:
        """
        Enable a connector in a project.
        
        Args:
            project_id: The project ID
            connector_name: Name of the connector to enable
            
        Returns:
            True if enabled, False if not found
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return False
        
        connector = registry.get_connector(connector_name)
        if not connector:
            return False
        
        connector.enabled = True
        
        logger.info(
            "Connector enabled",
            extra={
                "project_id": project_id,
                "connector_name": connector_name
            }
        )
        
        return True
    
    def disable_connector(
        self,
        project_id: str,
        connector_name: str
    ) -> bool:
        """
        Disable a connector in a project.
        
        Args:
            project_id: The project ID
            connector_name: Name of the connector to disable
            
        Returns:
            True if disabled, False if not found
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return False
        
        connector = registry.get_connector(connector_name)
        if not connector:
            return False
        
        connector.enabled = False
        
        logger.info(
            "Connector disabled",
            extra={
                "project_id": project_id,
                "connector_name": connector_name
            }
        )
        
        return True
    
    def get_project_connectors(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all connectors for a project with their metadata.
        
        Args:
            project_id: The project ID
            
        Returns:
            List of connector metadata dictionaries
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return []
        
        connectors = []
        for connector in registry.list_connectors().values():
            connectors.append({
                "name": connector.name,
                "version": connector.version,
                "enabled": connector.enabled,
                "tool_count": len(connector.tools),
                "loaded_at": connector.loaded_at.isoformat(),
                "file_path": str(connector.file_path) if connector.file_path else None,
                "config": connector.config
            })
        
        return connectors
    
    def get_project_tools(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all available tools for a project.
        
        Args:
            project_id: The project ID
            
        Returns:
            List of tool metadata dictionaries
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return []
        
        tools = []
        for tool in registry.list_all_tools().values():
            tools.append({
                "name": tool.name,
                "connector_name": tool.connector_name,
                "connector_version": tool.connector_version,
                "description": tool.definition.description,
                "input_schema": tool.definition.input_schema,
                "output_schema": tool.definition.output_schema,
                "endpoint": tool.definition.endpoint,
                "auth_type": tool.definition.auth.type,
                "loaded_at": tool.loaded_at.isoformat(),
                "last_used": tool.last_used.isoformat() if tool.last_used else None,
                "invocation_count": tool.invocation_count
            })
        
        return tools
    
    def get_tool_definition(
        self,
        project_id: str,
        tool_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific tool definition.
        
        Args:
            project_id: The project ID
            tool_name: Name of the tool
            
        Returns:
            Tool definition dictionary or None if not found
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return None
        
        tool = registry.get_tool(tool_name)
        if not tool:
            return None
        
        return {
            "name": tool.name,
            "connector_name": tool.connector_name,
            "connector_version": tool.connector_version,
            "description": tool.definition.description,
            "input_schema": tool.definition.input_schema,
            "output_schema": tool.definition.output_schema,
            "endpoint": tool.definition.endpoint,
            "auth_type": tool.definition.auth.type,
            "loaded_at": tool.loaded_at.isoformat(),
            "last_used": tool.last_used.isoformat() if tool.last_used else None,
            "invocation_count": tool.invocation_count
        }
    
    def mark_tool_used(
        self,
        project_id: str,
        tool_name: str
    ) -> bool:
        """
        Mark a tool as used (for analytics).
        
        Args:
            project_id: The project ID
            tool_name: Name of the tool
            
        Returns:
            True if marked, False if not found
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return False
        
        tool = registry.get_tool(tool_name)
        if not tool:
            return False
        
        tool.mark_used()
        return True
    
    def get_project_stats(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a project registry.
        
        Args:
            project_id: The project ID
            
        Returns:
            Statistics dictionary or None if project not found
        """
        registry = self.registry.get_project_registry(project_id)
        if not registry:
            return None
        
        return {
            "project_id": project_id,
            "tenant_id": registry.tenant_id,
            "created_at": registry.created_at.isoformat(),
            "last_updated": registry.last_updated.isoformat(),
            "connector_count": registry.get_connector_count(),
            "tool_count": registry.get_tool_count(),
            "enabled_connectors": sum(
                1 for c in registry.connectors.values() if c.enabled
            ),
            "disabled_connectors": sum(
                1 for c in registry.connectors.values() if not c.enabled
            )
        }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global registry statistics.
        
        Returns:
            Global statistics dictionary
        """
        return self.registry.get_registry_stats()
    
    async def perform_hot_reload_check(self, project_id: str) -> List[str]:
        """
        Check for files that need hot-reload and perform the reload.
        
        Args:
            project_id: The project ID to check
            
        Returns:
            List of connector names that were reloaded
        """
        updated_connectors = self.registry.check_for_updates(project_id)
        reloaded = []
        
        for connector_name in updated_connectors:
            success = await self.registry.hot_reload_connector(project_id, connector_name)
            if success:
                reloaded.append(connector_name)
        
        if reloaded:
            logger.info(
                "Hot-reload completed",
                extra={
                    "project_id": project_id,
                    "reloaded_connectors": reloaded
                }
            )
        
        return reloaded
    
    def install_sample_connectors(self, project_id: str, tenant_id: str) -> List[str]:
        """
        Install sample connectors for demonstration purposes.
        
        Args:
            project_id: The project ID
            tenant_id: The tenant ID
            
        Returns:
            List of installed connector names
        """
        installed = []
        samples_dir = Path(__file__).parent.parent / "samples"
        
        for sample_file in samples_dir.glob("*.yaml"):
            try:
                connector = self.install_connector_from_file(
                    project_id=project_id,
                    tenant_id=tenant_id,
                    file_path=sample_file,
                    enabled=True
                )
                installed.append(connector.name)
            except Exception as e:
                logger.warning(
                    "Failed to install sample connector",
                    extra={
                        "project_id": project_id,
                        "sample_file": str(sample_file),
                        "error": str(e)
                    }
                )
        
        return installed


# Global service instance
_service_instance: Optional[RegistryService] = None


def get_registry_service() -> RegistryService:
    """Get the global registry service instance (singleton)."""
    global _service_instance
    if _service_instance is None:
        _service_instance = RegistryService()
    return _service_instance


def reset_registry_service() -> None:
    """Reset the global registry service instance (for testing)."""
    global _service_instance
    _service_instance = None
