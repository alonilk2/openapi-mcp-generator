"""
MCP Runtime Orchestrator

The Python runtime component of the MCP + "npm of APIs" platform.
This package provides the core models and validation for connector manifests.

For P0-1 phase, this includes:
- Connector manifest models with Pydantic validation
- JSON Schema validation for tool inputs/outputs
- YAML/JSON serialization support
- Comprehensive test coverage

Future phases will add:
- Runtime orchestration and tool execution
- Authentication and authorization
- Rate limiting and caching
- Integration with Registry API and Azure services
"""

__version__ = "0.1.0a1"
__author__ = "MCP Platform Team"

from .models import ConnectorManifest, ConnectorTool, ToolAuth

__all__ = [
    "ConnectorManifest",
    "ConnectorTool", 
    "ToolAuth",
    "__version__",
    "__author__"
]
