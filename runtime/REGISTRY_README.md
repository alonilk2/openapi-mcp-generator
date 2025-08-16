# Internal Registry System

The internal registry system provides a comprehensive solution for managing installed descriptors and loaded tool definitions in memory on a per-project basis. It includes version tracking, hot-reload capabilities, and thread-safe operations.

## Architecture

### Core Components

1. **`LoadedTool`** - Represents a loaded tool definition with runtime information
2. **`LoadedConnector`** - Represents a loaded connector with its manifest and tools
3. **`ProjectRegistry`** - Registry for a single project's connectors and tools
4. **`InternalRegistry`** - Global registry managing all project registries
5. **`RegistryService`** - Service layer providing high-level operations

### Key Features

- **Per-project isolation** - Each project has its own connector registry
- **Version tracking** - Maintains current descriptor version for each connector
- **Hot-reload support** - Automatically detects file changes and reloads connectors
- **Thread-safe operations** - Uses RLock for concurrent access
- **Tool analytics** - Tracks tool usage statistics
- **Enable/disable connectors** - Runtime control over connector availability

## Usage

### Basic Setup

```python
from core.registry_service import get_registry_service

# Get the global registry service
registry_service = get_registry_service()

# Ensure a project registry exists
project_id = "my-project"
tenant_id = "my-tenant"
registry_service.ensure_project_registry(project_id, tenant_id)
```

### Installing Connectors

#### From File
```python
from pathlib import Path

# Install from YAML descriptor file
connector = registry_service.install_connector_from_file(
    project_id=project_id,
    tenant_id=tenant_id,
    file_path=Path("connectors/weather-api.yaml"),
    enabled=True
)
```

#### From Manifest Object
```python
from models.manifest import ConnectorManifest

# Load manifest from YAML data
manifest = ConnectorManifest.from_yaml_dict(yaml_data)

# Install from manifest
connector = registry_service.install_connector_from_manifest(
    project_id=project_id,
    tenant_id=tenant_id,
    manifest=manifest,
    config={"api_key": "secret"},
    enabled=True
)
```

### Managing Connectors

```python
# Enable/disable connectors
registry_service.enable_connector(project_id, "weather-api")
registry_service.disable_connector(project_id, "weather-api")

# Uninstall connector
registry_service.uninstall_connector(project_id, "weather-api")

# List all connectors
connectors = registry_service.get_project_connectors(project_id)
```

### Working with Tools

```python
# List all available tools
tools = registry_service.get_project_tools(project_id)

# Get specific tool definition
tool_def = registry_service.get_tool_definition(project_id, "get_weather")

# Mark tool as used (for analytics)
registry_service.mark_tool_used(project_id, "get_weather")
```

### Hot-Reload

```python
# Check for file changes and reload updated connectors
reloaded = await registry_service.perform_hot_reload_check(project_id)
print(f"Reloaded connectors: {reloaded}")
```

### Statistics

```python
# Get project statistics
stats = registry_service.get_project_stats(project_id)
print(f"Connectors: {stats['connector_count']}")
print(f"Tools: {stats['tool_count']}")

# Get global registry statistics
global_stats = registry_service.get_global_stats()
print(f"Total projects: {global_stats['total_projects']}")
```

## API Endpoints

The registry integrates with the FastAPI application through new endpoints:

### Connector Management
- `POST /v1/projects/{project_id}/connectors/install-from-file` - Install from file
- `POST /v1/projects/{project_id}/connectors/install-from-manifest` - Install from manifest
- `DELETE /v1/projects/{project_id}/connectors/{connector_name}` - Uninstall connector
- `POST /v1/projects/{project_id}/connectors/{connector_name}/enable` - Enable connector
- `POST /v1/projects/{project_id}/connectors/{connector_name}/disable` - Disable connector

### Discovery and Inspection
- `GET /v1/projects/{project_id}/connectors` - List all connectors
- `GET /v1/projects/{project_id}/tools` - List all tools
- `GET /v1/projects/{project_id}/tools/{tool_name}` - Get tool definition
- `GET /v1/projects/{project_id}/stats` - Get project statistics

### Utilities
- `POST /v1/projects/{project_id}/hot-reload` - Perform hot-reload check
- `POST /v1/projects/{project_id}/install-samples` - Install sample connectors

## Configuration

The registry respects the following configuration settings:

```python
# In core/config.py
HOT_RELOAD: bool = Field(default=False, description="Enable hot reload for connectors")
MAX_CONCURRENT_CONNECTORS: int = Field(default=100, description="Maximum concurrent connector instances")
```

## Data Models

### LoadedTool
- `name: str` - Tool name
- `connector_name: str` - Parent connector name
- `connector_version: str` - Parent connector version
- `definition: ConnectorTool` - Tool definition from manifest
- `loaded_at: datetime` - When the tool was loaded
- `last_used: Optional[datetime]` - Last usage timestamp
- `invocation_count: int` - Number of times invoked

### LoadedConnector
- `name: str` - Connector name
- `version: str` - Connector version
- `manifest: ConnectorManifest` - Complete connector manifest
- `tools: Dict[str, LoadedTool]` - Dictionary of loaded tools
- `loaded_at: datetime` - When the connector was loaded
- `file_path: Optional[Path]` - Source file path (for hot-reload)
- `file_mtime: Optional[float]` - File modification time
- `enabled: bool` - Whether the connector is enabled
- `config: Dict[str, Any]` - Runtime configuration

### ProjectRegistry
- `project_id: str` - Project identifier
- `tenant_id: str` - Tenant identifier
- `connectors: Dict[str, LoadedConnector]` - Dictionary of connectors
- `created_at: datetime` - Registry creation time
- `last_updated: datetime` - Last modification time

## Thread Safety

The registry system is designed to be thread-safe:

- Uses `threading.RLock` for all critical sections
- Atomic operations for adding/removing connectors
- Safe iteration over collections
- Proper exception handling

## Error Handling

The system provides comprehensive error handling:

- `MCPRuntimeException` for registry-specific errors
- Validation errors for malformed manifests
- File system errors for missing/corrupted descriptors
- Thread safety exceptions

## Testing

Run the demonstration script to see the registry in action:

```bash
cd runtime
python test_registry.py
```

This will demonstrate:
- Creating project registries
- Installing connectors from files
- Managing connector state
- Tool discovery and usage tracking
- Hot-reload functionality
- Statistics and monitoring

## Best Practices

1. **Always use the service layer** - Use `RegistryService` instead of direct registry access
2. **Handle tenant isolation** - Always provide tenant_id for proper isolation
3. **Enable hot-reload in development** - Set `HOT_RELOAD=true` for development
4. **Monitor statistics** - Use the stats endpoints to monitor system health
5. **Proper error handling** - Always catch and handle registry exceptions
6. **Version management** - Use semantic versioning for connector descriptors

## Extension Points

The registry system is designed for extensibility:

1. **Custom authentication** - Extend `ToolAuth` for new auth types
2. **Additional metadata** - Add fields to `LoadedTool` and `LoadedConnector`
3. **Storage backends** - Replace in-memory storage with persistent storage
4. **Event system** - Add hooks for connector load/unload events
5. **Caching strategies** - Implement caching for frequently accessed tools
