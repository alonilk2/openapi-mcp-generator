"""
Test script to demonstrate the internal registry functionality.

This script shows how to use the internal registry to manage
connectors and tools per project, including hot-reload capabilities.
"""

import asyncio
import logging
from pathlib import Path

from core.registry import get_registry, reset_registry
from core.registry_service import get_registry_service, reset_registry_service
from models.manifest import ConnectorManifest


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def demonstrate_registry():
    """Demonstrate the registry functionality."""
    
    print("=== Internal Registry Demonstration ===\n")
    
    # Reset registries for clean demo
    reset_registry()
    reset_registry_service()
    
    # Get registry service
    registry_service = get_registry_service()
    
    # Demo project and tenant IDs
    project_id = "demo-project-001"
    tenant_id = "tenant-demo"
    
    print(f"1. Creating project registry for project: {project_id}")
    print(f"   Tenant: {tenant_id}")
    
    # Ensure project registry exists
    project_registry = registry_service.ensure_project_registry(project_id, tenant_id)
    print(f"   ✓ Project registry created at: {project_registry.created_at}")
    
    # Get samples directory
    samples_dir = Path(__file__).parent / "samples"
    print(f"\n2. Looking for sample connectors in: {samples_dir}")
    
    # Install sample connectors
    installed_connectors = []
    for sample_file in samples_dir.glob("*.yaml"):
        try:
            print(f"   Installing: {sample_file.name}")
            connector = registry_service.install_connector_from_file(
                project_id=project_id,
                tenant_id=tenant_id,
                file_path=sample_file,
                enabled=True
            )
            installed_connectors.append(connector)
            print(f"   ✓ Installed {connector.name} v{connector.version} with {len(connector.tools)} tools")
        except Exception as e:
            print(f"   ✗ Failed to install {sample_file.name}: {e}")
    
    print(f"\n3. Installed {len(installed_connectors)} connectors")
    
    # List all connectors
    print("\n4. Listing all connectors in project:")
    connectors = registry_service.get_project_connectors(project_id)
    for connector in connectors:
        status = "enabled" if connector["enabled"] else "disabled"
        print(f"   - {connector['name']} v{connector['version']} ({status}) - {connector['tool_count']} tools")
    
    # List all tools
    print("\n5. Listing all available tools:")
    tools = registry_service.get_project_tools(project_id)
    for tool in tools:
        print(f"   - {tool['name']} (from {tool['connector_name']})")
        print(f"     Description: {tool['description']}")
        print(f"     Endpoint: {tool['endpoint']}")
    
    # Get a specific tool definition
    if tools:
        tool_name = tools[0]['name']
        print(f"\n6. Getting definition for tool: {tool_name}")
        tool_def = registry_service.get_tool_definition(project_id, tool_name)
        if tool_def:
            print(f"   Tool: {tool_def['name']}")
            print(f"   Connector: {tool_def['connector_name']} v{tool_def['connector_version']}")
            print(f"   Description: {tool_def['description']}")
            print(f"   Input Schema Keys: {list(tool_def['input_schema'].get('properties', {}).keys())}")
            print(f"   Output Schema Keys: {list(tool_def['output_schema'].get('properties', {}).keys())}")
    
    # Mark tool as used (for analytics)
    if tools:
        tool_name = tools[0]['name']
        print(f"\n7. Marking tool as used: {tool_name}")
        success = registry_service.mark_tool_used(project_id, tool_name)
        print(f"   ✓ Tool marked as used: {success}")
        
        # Get updated tool definition to see usage stats
        tool_def = registry_service.get_tool_definition(project_id, tool_name)
        if tool_def:
            print(f"   Invocation count: {tool_def['invocation_count']}")
            print(f"   Last used: {tool_def['last_used']}")
    
    # Test enable/disable connector
    if connectors:
        connector_name = connectors[0]['name']
        print(f"\n8. Testing enable/disable for connector: {connector_name}")
        
        # Disable connector
        success = registry_service.disable_connector(project_id, connector_name)
        print(f"   ✓ Disabled connector: {success}")
        
        # Check tool count after disabling
        stats = registry_service.get_project_stats(project_id)
        if stats:
            print(f"   Active tools after disable: {stats['tool_count']}")
        
        # Re-enable connector
        success = registry_service.enable_connector(project_id, connector_name)
        print(f"   ✓ Re-enabled connector: {success}")
        
        # Check tool count after re-enabling
        stats = registry_service.get_project_stats(project_id)
        if stats:
            print(f"   Active tools after enable: {stats['tool_count']}")
    
    # Get project statistics
    print("\n9. Project statistics:")
    stats = registry_service.get_project_stats(project_id)
    if stats:
        print(f"   Project ID: {stats['project_id']}")
        print(f"   Tenant ID: {stats['tenant_id']}")
        print(f"   Created: {stats['created_at']}")
        print(f"   Last updated: {stats['last_updated']}")
        print(f"   Total connectors: {stats['connector_count']}")
        print(f"   Total tools: {stats['tool_count']}")
        print(f"   Enabled connectors: {stats['enabled_connectors']}")
        print(f"   Disabled connectors: {stats['disabled_connectors']}")
    
    # Get global registry statistics
    print("\n10. Global registry statistics:")
    global_stats = registry_service.get_global_stats()
    print(f"    Total projects: {global_stats['total_projects']}")
    print(f"    Total connectors: {global_stats['total_connectors']}")
    print(f"    Total tools: {global_stats['total_tools']}")
    print(f"    Hot reload enabled: {global_stats['hot_reload_enabled']}")
    
    # Test hot-reload check (if enabled)
    print("\n11. Testing hot-reload check:")
    try:
        reloaded = await registry_service.perform_hot_reload_check(project_id)
        print(f"    Connectors reloaded: {len(reloaded)}")
        if reloaded:
            print(f"    Reloaded: {', '.join(reloaded)}")
        else:
            print("    No connectors needed reloading")
    except Exception as e:
        print(f"    Hot-reload check failed: {e}")
    
    # Test uninstalling a connector
    if connectors:
        connector_name = connectors[0]['name']
        print(f"\n12. Uninstalling connector: {connector_name}")
        success = registry_service.uninstall_connector(project_id, connector_name)
        print(f"    ✓ Uninstalled: {success}")
        
        # Check final stats
        final_stats = registry_service.get_project_stats(project_id)
        if final_stats:
            print(f"    Remaining connectors: {final_stats['connector_count']}")
            print(f"    Remaining tools: {final_stats['tool_count']}")
    
    print("\n=== Registry Demonstration Complete ===")


async def demonstrate_manifest_loading():
    """Demonstrate loading connectors from manifest objects."""
    
    print("\n=== Manifest Loading Demonstration ===")
    
    # Create a sample manifest programmatically
    manifest_data = {
        "connector": {
            "name": "demo-calculator",
            "version": "1.0.0",
            "tools": [
                {
                    "name": "add",
                    "description": "Add two numbers",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"}
                        },
                        "required": ["a", "b"]
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "number", "description": "Sum of a and b"}
                        },
                        "required": ["result"]
                    },
                    "endpoint": "math.add",
                    "auth": {"type": "none"}
                },
                {
                    "name": "multiply",
                    "description": "Multiply two numbers",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"}
                        },
                        "required": ["a", "b"]
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "result": {"type": "number", "description": "Product of a and b"}
                        },
                        "required": ["result"]
                    },
                    "endpoint": "math.multiply",
                    "auth": {"type": "none"}
                }
            ]
        }
    }
    
    try:
        # Create manifest from data
        manifest = ConnectorManifest.from_yaml_dict(manifest_data)
        print(f"✓ Created manifest for: {manifest.name} v{manifest.version}")
        print(f"  Tools: {', '.join([tool.name for tool in manifest.tools])}")
        
        # Install connector from manifest
        registry_service = get_registry_service()
        project_id = "demo-project-002"
        tenant_id = "tenant-demo"
        
        connector = registry_service.install_connector_from_manifest(
            project_id=project_id,
            tenant_id=tenant_id,
            manifest=manifest,
            config={"demo": True},
            enabled=True
        )
        
        print(f"✓ Installed connector from manifest: {connector.name}")
        print(f"  Tools loaded: {len(connector.tools)}")
        print(f"  Configuration: {connector.config}")
        
        # List tools
        tools = registry_service.get_project_tools(project_id)
        print(f"  Available tools: {', '.join([tool['name'] for tool in tools])}")
        
    except Exception as e:
        print(f"✗ Failed to load connector from manifest: {e}")
    
    print("=== Manifest Loading Complete ===")


if __name__ == "__main__":
    # Run the demonstrations
    asyncio.run(demonstrate_registry())
    asyncio.run(demonstrate_manifest_loading())
