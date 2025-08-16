"""
Internal registry for managing installed descriptors and loaded tool definitions.

This module provides an in-memory registry that maps per-project installed
connector descriptors to their loaded tool definitions, maintaining version
information and supporting hot-reload capabilities.
"""

import logging
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from pathlib import Path

import yaml
from pydantic import ValidationError

from models.manifest import ConnectorManifest, ConnectorTool
from core.config import get_settings
from core.exceptions import MCPRuntimeException


logger = logging.getLogger(__name__)


@dataclass
class LoadedTool:
    """
    Represents a loaded tool definition with runtime information.
    """
    name: str
    connector_name: str
    connector_version: str
    definition: ConnectorTool
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: Optional[datetime] = None
    invocation_count: int = 0
    
    def mark_used(self) -> None:
        """Mark this tool as recently used."""
        self.last_used = datetime.now(timezone.utc)
        self.invocation_count += 1


@dataclass
class LoadedConnector:
    """
    Represents a loaded connector with its manifest and tools.
    """
    name: str
    version: str
    manifest: ConnectorManifest
    tools: Dict[str, LoadedTool]
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    file_path: Optional[Path] = None
    file_mtime: Optional[float] = None
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    
    def get_tool(self, tool_name: str) -> Optional[LoadedTool]:
        """Get a tool by name."""
        return self.tools.get(tool_name)
    
    def list_tool_names(self) -> List[str]:
        """Get list of all tool names in this connector."""
        return list(self.tools.keys())
    
    def get_enabled_tools(self) -> Dict[str, LoadedTool]:
        """Get only enabled tools when connector is enabled."""
        if not self.enabled:
            return {}
        return self.tools.copy()


@dataclass
class ProjectRegistry:
    """
    Registry for a single project's connectors and tools.
    """
    project_id: str
    tenant_id: str
    connectors: Dict[str, LoadedConnector] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_connector(self, connector: LoadedConnector) -> None:
        """Add or update a connector in the registry."""
        self.connectors[connector.name] = connector
        self.last_updated = datetime.now(timezone.utc)
        logger.info(
            "Connector added to project registry",
            extra={
                "project_id": self.project_id,
                "connector_name": connector.name,
                "connector_version": connector.version,
                "tool_count": len(connector.tools)
            }
        )
    
    def remove_connector(self, connector_name: str) -> bool:
        """Remove a connector from the registry."""
        if connector_name in self.connectors:
            del self.connectors[connector_name]
            self.last_updated = datetime.now(timezone.utc)
            logger.info(
                "Connector removed from project registry",
                extra={
                    "project_id": self.project_id,
                    "connector_name": connector_name
                }
            )
            return True
        return False
    
    def get_connector(self, connector_name: str) -> Optional[LoadedConnector]:
        """Get a connector by name."""
        return self.connectors.get(connector_name)
    
    def list_connectors(self) -> Dict[str, LoadedConnector]:
        """Get all connectors in this project."""
        return self.connectors.copy()
    
    def get_tool(self, tool_name: str) -> Optional[LoadedTool]:
        """
        Get a tool by name across all connectors.
        Returns the first matching tool found.
        """
        for connector in self.connectors.values():
            if not connector.enabled:
                continue
            tool = connector.get_tool(tool_name)
            if tool:
                return tool
        return None
    
    def get_tool_by_connector(self, connector_name: str, tool_name: str) -> Optional[LoadedTool]:
        """Get a tool by name from a specific connector."""
        connector = self.get_connector(connector_name)
        if connector and connector.enabled:
            return connector.get_tool(tool_name)
        return None
    
    def list_all_tools(self) -> Dict[str, LoadedTool]:
        """Get all tools from all enabled connectors."""
        all_tools = {}
        for connector in self.connectors.values():
            if connector.enabled:
                all_tools.update(connector.get_enabled_tools())
        return all_tools
    
    def get_tool_count(self) -> int:
        """Get total count of tools across all enabled connectors."""
        return sum(
            len(connector.tools) 
            for connector in self.connectors.values() 
            if connector.enabled
        )
    
    def get_connector_count(self) -> int:
        """Get count of enabled connectors."""
        return sum(1 for connector in self.connectors.values() if connector.enabled)


class InternalRegistry:
    """
    Global registry managing all project registries and their connectors.
    
    This class provides thread-safe operations for managing per-project
    connector registries with hot-reload capabilities.
    """
    
    def __init__(self):
        self._registries: Dict[str, ProjectRegistry] = {}
        self._lock = RLock()
        self._file_watchers: Dict[str, Set[Path]] = {}
        self._settings = get_settings()
        
        logger.info("Internal registry initialized")
    
    def create_project_registry(self, project_id: str, tenant_id: str) -> ProjectRegistry:
        """Create a new project registry."""
        with self._lock:
            if project_id in self._registries:
                logger.warning(
                    "Project registry already exists", 
                    extra={"project_id": project_id}
                )
                return self._registries[project_id]
            
            registry = ProjectRegistry(project_id=project_id, tenant_id=tenant_id)
            self._registries[project_id] = registry
            self._file_watchers[project_id] = set()
            
            logger.info(
                "Project registry created",
                extra={
                    "project_id": project_id,
                    "tenant_id": tenant_id
                }
            )
            return registry
    
    def get_project_registry(self, project_id: str) -> Optional[ProjectRegistry]:
        """Get a project registry by ID."""
        with self._lock:
            return self._registries.get(project_id)
    
    def remove_project_registry(self, project_id: str) -> bool:
        """Remove a project registry."""
        with self._lock:
            if project_id in self._registries:
                del self._registries[project_id]
                if project_id in self._file_watchers:
                    del self._file_watchers[project_id]
                
                logger.info(
                    "Project registry removed",
                    extra={"project_id": project_id}
                )
                return True
            return False
    
    def list_projects(self) -> List[str]:
        """Get list of all project IDs."""
        with self._lock:
            return list(self._registries.keys())
    
    def load_connector_from_file(
        self, 
        project_id: str, 
        file_path: Path, 
        config: Optional[Dict[str, Any]] = None
    ) -> LoadedConnector:
        """
        Load a connector from a YAML descriptor file.
        
        Args:
            project_id: The project ID to load the connector for
            file_path: Path to the YAML descriptor file
            config: Optional configuration override
            
        Returns:
            LoadedConnector instance
            
        Raises:
            MCPRuntimeException: If loading fails
        """
        try:
            if not file_path.exists():
                raise MCPRuntimeException(
                    message=f"Connector descriptor file not found: {file_path}",
                    error_type="FILE_NOT_FOUND",
                    status_code=404
                )
            
            # Read and parse YAML
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Validate and create manifest
            manifest = ConnectorManifest.from_yaml_dict(data)
            
            # Create loaded tools
            tools = {}
            for tool_def in manifest.tools:
                loaded_tool = LoadedTool(
                    name=tool_def.name,
                    connector_name=manifest.name,
                    connector_version=manifest.version,
                    definition=tool_def
                )
                tools[tool_def.name] = loaded_tool
            
            # Get file modification time for hot-reload
            file_mtime = file_path.stat().st_mtime
            
            # Create loaded connector
            connector = LoadedConnector(
                name=manifest.name,
                version=manifest.version,
                manifest=manifest,
                tools=tools,
                file_path=file_path,
                file_mtime=file_mtime,
                config=config or {}
            )
            
            # Add to file watchers for hot-reload
            with self._lock:
                if project_id in self._file_watchers:
                    self._file_watchers[project_id].add(file_path)
            
            logger.info(
                "Connector loaded from file",
                extra={
                    "project_id": project_id,
                    "connector_name": manifest.name,
                    "connector_version": manifest.version,
                    "file_path": str(file_path),
                    "tool_count": len(tools)
                }
            )
            
            return connector
            
        except ValidationError as e:
            raise MCPRuntimeException(
                message=f"Invalid connector descriptor: {e}",
                error_type="VALIDATION_ERROR",
                status_code=400,
                details={"validation_errors": e.errors()}
            )
        except yaml.YAMLError as e:
            raise MCPRuntimeException(
                message=f"Invalid YAML in connector descriptor: {e}",
                error_type="YAML_ERROR",
                status_code=400
            )
        except Exception as e:
            logger.exception("Unexpected error loading connector from file")
            raise MCPRuntimeException(
                message=f"Failed to load connector: {e}",
                error_type="LOAD_ERROR",
                status_code=500
            )
    
    def load_connector_from_manifest(
        self,
        project_id: str,
        manifest: ConnectorManifest,
        config: Optional[Dict[str, Any]] = None
    ) -> LoadedConnector:
        """
        Load a connector from a manifest object.
        
        Args:
            project_id: The project ID to load the connector for
            manifest: ConnectorManifest instance
            config: Optional configuration override
            
        Returns:
            LoadedConnector instance
        """
        try:
            # Create loaded tools
            tools = {}
            for tool_def in manifest.tools:
                loaded_tool = LoadedTool(
                    name=tool_def.name,
                    connector_name=manifest.name,
                    connector_version=manifest.version,
                    definition=tool_def
                )
                tools[tool_def.name] = loaded_tool
            
            # Create loaded connector
            connector = LoadedConnector(
                name=manifest.name,
                version=manifest.version,
                manifest=manifest,
                tools=tools,
                config=config or {}
            )
            
            logger.info(
                "Connector loaded from manifest",
                extra={
                    "project_id": project_id,
                    "connector_name": manifest.name,
                    "connector_version": manifest.version,
                    "tool_count": len(tools)
                }
            )
            
            return connector
            
        except Exception as e:
            logger.exception("Unexpected error loading connector from manifest")
            raise MCPRuntimeException(
                message=f"Failed to load connector: {e}",
                error_type="LOAD_ERROR",
                status_code=500
            )
    
    def install_connector(
        self,
        project_id: str,
        connector: LoadedConnector,
        replace_existing: bool = True
    ) -> bool:
        """
        Install a connector into a project registry.
        
        Args:
            project_id: The project ID to install the connector in
            connector: LoadedConnector to install
            replace_existing: Whether to replace existing connector with same name
            
        Returns:
            True if installed, False if already exists and replace_existing=False
        """
        with self._lock:
            registry = self._registries.get(project_id)
            if not registry:
                raise MCPRuntimeException(
                    message=f"Project registry not found: {project_id}",
                    error_type="PROJECT_NOT_FOUND",
                    status_code=404
                )
            
            existing = registry.get_connector(connector.name)
            if existing and not replace_existing:
                logger.warning(
                    "Connector already exists and replace_existing=False",
                    extra={
                        "project_id": project_id,
                        "connector_name": connector.name,
                        "existing_version": existing.version,
                        "new_version": connector.version
                    }
                )
                return False
            
            registry.add_connector(connector)
            return True
    
    def uninstall_connector(self, project_id: str, connector_name: str) -> bool:
        """
        Uninstall a connector from a project registry.
        
        Args:
            project_id: The project ID to uninstall from
            connector_name: Name of the connector to uninstall
            
        Returns:
            True if uninstalled, False if not found
        """
        with self._lock:
            registry = self._registries.get(project_id)
            if not registry:
                return False
            
            # Remove from file watchers
            connector = registry.get_connector(connector_name)
            if connector and connector.file_path and project_id in self._file_watchers:
                self._file_watchers[project_id].discard(connector.file_path)
            
            return registry.remove_connector(connector_name)
    
    def check_for_updates(self, project_id: str) -> List[str]:
        """
        Check for file updates that require hot-reload.
        
        Args:
            project_id: The project ID to check
            
        Returns:
            List of connector names that need to be reloaded
        """
        if not self._settings.HOT_RELOAD:
            return []
        
        updated_connectors = []
        
        with self._lock:
            registry = self._registries.get(project_id)
            if not registry:
                return updated_connectors
            
            for connector in registry.connectors.values():
                if not connector.file_path or not connector.file_mtime:
                    continue
                
                try:
                    current_mtime = connector.file_path.stat().st_mtime
                    if current_mtime > connector.file_mtime:
                        updated_connectors.append(connector.name)
                        logger.info(
                            "File modification detected for hot-reload",
                            extra={
                                "project_id": project_id,
                                "connector_name": connector.name,
                                "file_path": str(connector.file_path),
                                "old_mtime": connector.file_mtime,
                                "new_mtime": current_mtime
                            }
                        )
                except OSError:
                    # File might have been deleted
                    logger.warning(
                        "Connector file no longer accessible",
                        extra={
                            "project_id": project_id,
                            "connector_name": connector.name,
                            "file_path": str(connector.file_path)
                        }
                    )
        
        return updated_connectors
    
    async def hot_reload_connector(self, project_id: str, connector_name: str) -> bool:
        """
        Hot-reload a connector from its file.
        
        Args:
            project_id: The project ID
            connector_name: Name of the connector to reload
            
        Returns:
            True if reloaded successfully, False otherwise
        """
        if not self._settings.HOT_RELOAD:
            logger.warning("Hot reload is disabled")
            return False
        
        try:
            with self._lock:
                registry = self._registries.get(project_id)
                if not registry:
                    return False
                
                old_connector = registry.get_connector(connector_name)
                if not old_connector or not old_connector.file_path:
                    return False
                
                # Preserve configuration
                old_config = old_connector.config
                old_enabled = old_connector.enabled
            
            # Load new connector (outside lock to avoid blocking)
            new_connector = self.load_connector_from_file(
                project_id, 
                old_connector.file_path, 
                old_config
            )
            new_connector.enabled = old_enabled
            
            # Install new connector
            self.install_connector(project_id, new_connector, replace_existing=True)
            
            logger.info(
                "Connector hot-reloaded successfully",
                extra={
                    "project_id": project_id,
                    "connector_name": connector_name,
                    "old_version": old_connector.version,
                    "new_version": new_connector.version
                }
            )
            return True
            
        except Exception as e:
            logger.exception(
                "Hot-reload failed",
                extra={
                    "project_id": project_id,
                    "connector_name": connector_name,
                    "error": str(e)
                }
            )
            return False
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get overall registry statistics."""
        with self._lock:
            total_connectors = 0
            total_tools = 0
            
            for registry in self._registries.values():
                total_connectors += registry.get_connector_count()
                total_tools += registry.get_tool_count()
            
            return {
                "total_projects": len(self._registries),
                "total_connectors": total_connectors,
                "total_tools": total_tools,
                "hot_reload_enabled": self._settings.HOT_RELOAD
            }


# Global registry instance
_registry_instance: Optional[InternalRegistry] = None


def get_registry() -> InternalRegistry:
    """Get the global registry instance (singleton)."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = InternalRegistry()
    return _registry_instance


def reset_registry() -> None:
    """Reset the global registry instance (for testing)."""
    global _registry_instance
    _registry_instance = None
