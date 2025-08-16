"""
API module for the MCP Runtime Orchestrator.

This module contains all REST API endpoints organized by functional area:
- health: Health check and monitoring endpoints
- mcp: MCP protocol-specific endpoints  
- projects: Project management endpoints
- runtime: Runtime control and monitoring endpoints
"""

# Direct imports to avoid relative import issues
import api.health as health
import api.mcp as mcp
import api.projects as projects
import api.runtime as runtime

__all__ = ["health", "mcp", "projects", "runtime"]
