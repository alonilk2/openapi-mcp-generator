#!/usr/bin/env python3
"""
MCP Stdio Server Entry Point

This script provides a stdio-based MCP server interface that communicates
via standard input/output, compatible with VS Code and other MCP clients.

The server implements the MCP protocol over stdio, while delegating
actual tool execution to the HTTP-based runtime orchestrator.
"""

import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from core.config import get_settings
from core.builtin_tools import builtin_tool_handler
from core.registry import get_registry
from core.registry import LoadedTool
from core.registry_service import get_registry_service
from core.authenticated_client import get_tool_execution_client
from core.credential_resolver import CredentialResolutionError


class MCPStdioServer:
    """MCP server that communicates via stdio."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = self._setup_logging()
        self.request_id_counter = 0
        self.tool_execution_client = get_tool_execution_client()
        self._initialize_sample_connectors()
        
    def _initialize_sample_connectors(self) -> None:
        """Initialize sample connectors for demonstration."""
        try:
            registry_service = get_registry_service()
            project_id = "default"
            tenant_id = "default-tenant"
            
            # Install sample connectors
            installed = registry_service.install_sample_connectors(project_id, tenant_id)
            self.logger.info(f"Initialized {len(installed)} sample connectors: {', '.join(installed)}")
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize sample connectors: {e}")
        
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging to stderr (not stdout, which is used for MCP protocol)."""
        logger = logging.getLogger("mcp_stdio_server")
        logger.setLevel(logging.DEBUG if self.settings.DEBUG else logging.INFO)
        
        # Log to stderr to avoid interfering with stdio MCP communication
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
        
    def _send_response(self, response: Dict[str, Any]) -> None:
        """Send a JSON-RPC response to stdout."""
        response_json = json.dumps(response, separators=(',', ':'))
        print(response_json, flush=True)
        self.logger.debug(f"Sent response: {response_json}")
        
    def _send_error(self, request_id: Optional[Any], code: int, message: str) -> None:
        """Send a JSON-RPC error response."""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }
        self._send_response(error_response)
        
    async def _handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> None:
        """Handle the initialize request."""
        self.logger.info("Handling initialize request")
        
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {
                        "listChanged": True
                    },
                    "resources": {},
                    "prompts": {},
                    "experimental": {}
                },
                "serverInfo": {
                    "name": "MCP Runtime Orchestrator",
                    "version": self.settings.VERSION
                }
            }
        }
        
        self._send_response(response)
        
    async def _handle_tools_list(self, request_id: Any, params: Dict[str, Any]) -> None:
        """Handle the tools/list request."""
        self.logger.info("Handling tools/list request")
        
        tools = []

        # Perform hot-reload check if enabled to pick up newly added manifests
        try:
            if self.settings.HOT_RELOAD:
                registry = get_registry()
                updated = registry.check_for_updates("default")
                if updated:
                    self.logger.info(
                        "Hot-reload: updating connectors before listing tools",
                        extra={"project_id": "default", "updated_connectors": updated}
                    )
                    for conn_name in updated:
                        try:
                            await registry.hot_reload_connector("default", conn_name)
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to hot-reload connector {conn_name}: {e}"
                            )
        except Exception as e:
            self.logger.warning(f"Hot-reload pre-check failed: {e}")

        # In development, rescan and (re)install sample connectors to pick up new files
        try:
            if self.settings.is_development():
                svc = get_registry_service()
                svc.ensure_project_registry("default", "default-tenant")
                installed = svc.install_sample_connectors("default", "default-tenant")
                if installed:
                    self.logger.info(
                        "Installed/updated sample connectors before listing tools",
                        extra={"project_id": "default", "installed": installed}
                    )
        except Exception as e:
            self.logger.warning(f"Sample rescan failed: {e}")
        
        # Get built-in tools
        for tool in builtin_tool_handler.list_tools():
            tool_schema = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            
            # Convert parameters to JSON schema
            for param in tool.parameters:
                tool_schema["inputSchema"]["properties"][param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.required:
                    tool_schema["inputSchema"]["required"].append(param.name)
            
            tools.append(tool_schema)
        
        # Get connector-provided tools
        registry = get_registry()
        project_registry = registry.get_project_registry("default")
        
        if project_registry:
            for connector_name, connector in project_registry.list_connectors().items():
                if not connector or not connector.enabled:
                    continue
                    
                for tool_name, loaded_tool in connector.get_enabled_tools().items():
                    tool_def = loaded_tool.definition
                    
                    tool_schema = {
                        "name": tool_name,
                        "description": tool_def.description,
                        "inputSchema": tool_def.input_schema or {
                            "type": "object",
                            "properties": {},
                            "required": []
                        }
                    }
                    
                    tools.append(tool_schema)
        
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools
            }
        }
        
        self._send_response(response)
        
    async def _handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> None:
        """Handle the tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        self.logger.info(f"Handling tools/call request for tool: {tool_name}")
        
        try:
            # Check if this is a built-in tool first
            if builtin_tool_handler.has_tool(tool_name):
                result = await builtin_tool_handler.execute_tool(tool_name, arguments)
                
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": result.content,
                        "isError": result.is_error
                    }
                }
                
                self._send_response(response)
                return
            
            # Check for connector tools
            registry = get_registry()
            project_registry = registry.get_project_registry("default")
            
            if project_registry:
                loaded_tool = project_registry.get_tool(tool_name)
                if loaded_tool:
                    # Mark tool as used for statistics
                    loaded_tool.mark_used()
                    
                    try:
                        # Get the connector to access its base URL
                        connector = project_registry.get_connector(loaded_tool.connector_name)
                        base_url = connector.manifest.base_url if connector else None
                        
                        # Execute real authenticated tool call
                        result = await self._execute_connector_tool_authenticated(
                            loaded_tool, arguments, base_url
                        )
                        
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": result,
                                "isError": False
                            }
                        }
                        
                        self._send_response(response)
                        return
                        
                    except CredentialResolutionError as e:
                        # No mock fallback: return error to client
                        self.logger.warning(f"Credential resolution failed for {tool_name}: {e}")
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [{
                                    "type": "text",
                                    "text": f"Authentication failed for tool '{tool_name}': {str(e)}",
                                }],
                                "isError": True
                            }
                        }
                        self._send_response(response)
                        return
                        
                    except Exception as e:
                        # No mock fallback: return execution error
                        self.logger.error(f"Error executing tool {tool_name}: {e}")
                        response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [{
                                    "type": "text",
                                    "text": f"Tool execution failed: {str(e)}",
                                }],
                                "isError": True
                            }
                        }
                        self._send_response(response)
                        return
            
            # Tool not found
            self._send_error(request_id, -32601, f"Tool '{tool_name}' not found")
            
        except Exception as e:
            self.logger.error(f"Error executing tool {tool_name}: {e}")
            self._send_error(request_id, -32603, f"Tool execution failed: {str(e)}")
            
    
        
    async def _execute_connector_tool_authenticated(self, loaded_tool: LoadedTool, arguments: Dict[str, Any], base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Real implementation of connector tool execution for P0-3 with authentication.
        
        This method uses the ToolExecutionClient to make authenticated HTTP requests
        to external APIs based on the tool's configuration and stored credentials.
        """
        tool_def = loaded_tool.definition
        connector_name = loaded_tool.connector_name
        
        self.logger.info(f"Executing authenticated tool '{tool_def.name}' from connector '{connector_name}'")
        self.logger.debug(f"Tool execution parameters - arguments: {arguments}, base_url: {base_url}")
        
        try:
            # Execute the tool using the authenticated client
            self.logger.debug(f"Calling tool_execution_client.execute_tool with:")
            self.logger.debug(f"  - tool: {tool_def.name} (endpoint: {tool_def.endpoint})")
            self.logger.debug(f"  - connector_name: {connector_name}")
            self.logger.debug(f"  - input_data: {arguments}")
            self.logger.debug(f"  - base_url: {base_url}")
            
            result_data = await self.tool_execution_client.execute_tool(
                tool=tool_def,
                connector_name=connector_name,
                input_data=arguments,
                base_url=base_url
            )
            
            self.logger.debug(f"Tool execution completed successfully")
            self.logger.debug(f"Raw result_data: {result_data}")
            
            # Format the result for MCP protocol
            formatted_result = [{"type": "text", "text": f"Tool execution result: {result_data}"}]
            self.logger.debug(f"Formatted MCP result: {formatted_result}")
            
            return formatted_result
            
        except CredentialResolutionError as e:
            # Re-raise credential errors so they can be handled by the caller
            self.logger.debug(f"Credential resolution error occurred: {e}")
            self.logger.debug(f"Error type: {type(e).__name__}")
            raise
        except Exception as e:
            self.logger.error(f"Authenticated tool execution failed: {e}")
            self.logger.debug(f"Exception type: {type(e).__name__}")
            self.logger.debug(f"Exception details: {str(e)}")
            if hasattr(e, '__dict__'):
                self.logger.debug(f"Exception attributes: {e.__dict__}")
            raise
        
    async def _handle_request(self, request: Dict[str, Any]) -> None:
        """Handle a single JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        
        self.logger.debug(f"Handling request: {method}")
        
        try:
            if method == "initialize":
                await self._handle_initialize(request_id, params)
            elif method == "tools/list":
                await self._handle_tools_list(request_id, params)
            elif method == "tools/call":
                await self._handle_tools_call(request_id, params)
            else:
                self._send_error(request_id, -32601, f"Method '{method}' not found")
                
        except Exception as e:
            self.logger.error(f"Error handling request {method}: {e}")
            self._send_error(request_id, -32603, f"Internal error: {str(e)}")
            
    async def run(self) -> None:
        """Main server loop - read from stdin and process requests."""
        self.logger.info("Starting MCP stdio server")
        
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                    
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    request = json.loads(line)
                    await self._handle_request(request)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Invalid JSON received: {e}")
                    self._send_error(None, -32700, "Parse error")
                    
        except KeyboardInterrupt:
            self.logger.info("Server interrupted")
        except Exception as e:
            self.logger.error(f"Server error: {e}")
        finally:
            self.logger.info("MCP stdio server stopping")


async def main():
    """Main entry point for the stdio server."""
    server = MCPStdioServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
