"""
Built-in tool handlers for the MCP Runtime Orchestrator.

This module provides MVP stub implementations for built-in tools
that don't require external connectors.
"""

import datetime
import logging
from typing import Any, Dict, List

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Tool parameter definition."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


class BuiltinTool(BaseModel):
    """Built-in tool definition."""
    name: str
    description: str
    parameters: List[ToolParameter]
    category: str = "builtin"


class ToolExecutionResult(BaseModel):
    """Result of tool execution."""
    content: List[Dict[str, Any]]
    is_error: bool = False
    execution_time_ms: int = 0


class BuiltinToolHandler:
    """Handler for built-in tools."""
    
    def __init__(self):
        """Initialize the built-in tool handler."""
        self._tools = self._register_builtin_tools()
    
    def _register_builtin_tools(self) -> Dict[str, BuiltinTool]:
        """Register all built-in tools."""
        tools = {}
        
        # Echo tool - returns input as output
        tools["echo"] = BuiltinTool(
            name="echo",
            description="Echo back the input text exactly as provided",
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="Text to echo back",
                    required=True
                )
            ]
        )
        
        # Hello tool - fixed response
        tools["hello"] = BuiltinTool(
            name="hello",
            description="Returns a friendly greeting message",
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description="Optional name to include in greeting",
                    required=False,
                    default="World"
                )
            ]
        )
        
        # Time tool - current timestamp
        tools["get_time"] = BuiltinTool(
            name="get_time",
            description="Get the current date and time",
            parameters=[
                ToolParameter(
                    name="format",
                    type="string",
                    description="Time format (iso, timestamp, or human)",
                    required=False,
                    default="iso"
                )
            ]
        )
        
        return tools
    
    def list_tools(self) -> List[BuiltinTool]:
        """Get all available built-in tools."""
        return list(self._tools.values())
    
    def get_tool(self, name: str) -> BuiltinTool:
        """Get a specific built-in tool by name."""
        if name not in self._tools:
            raise ValueError(f"Built-in tool '{name}' not found")
        return self._tools[name]
    
    def has_tool(self, name: str) -> bool:
        """Check if a built-in tool exists."""
        return name in self._tools
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """Execute a built-in tool."""
        start_time = datetime.datetime.now()
        
        try:
            if not self.has_tool(name):
                raise ValueError(f"Built-in tool '{name}' not found")
            
            logger.info(f"Executing built-in tool: {name}", extra={"arguments": arguments})
            
            # Route to appropriate handler
            if name == "echo":
                result = await self._handle_echo(arguments)
            elif name == "hello":
                result = await self._handle_hello(arguments)
            elif name == "get_time":
                result = await self._handle_get_time(arguments)
            else:
                raise ValueError(f"No handler implemented for tool '{name}'")
            
            # Calculate execution time
            end_time = datetime.datetime.now()
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            logger.info(
                f"Built-in tool '{name}' executed successfully",
                extra={
                    "execution_time_ms": execution_time_ms,
                    "result_content_count": len(result.content)
                }
            )
            
            result.execution_time_ms = execution_time_ms
            return result
            
        except Exception as e:
            # Calculate execution time even for errors
            end_time = datetime.datetime.now()
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
            
            logger.error(
                f"Built-in tool '{name}' execution failed",
                exc_info=True,
                extra={
                    "arguments": arguments,
                    "error": str(e),
                    "execution_time_ms": execution_time_ms
                }
            )
            
            return ToolExecutionResult(
                content=[{
                    "type": "text",
                    "text": f"Error executing built-in tool '{name}': {str(e)}"
                }],
                is_error=True,
                execution_time_ms=execution_time_ms
            )
    
    async def _handle_echo(self, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """Handle echo tool execution."""
        text = arguments.get("text", "")
        
        if not isinstance(text, str):
            raise ValueError("The 'text' parameter must be a string")
        
        return ToolExecutionResult(
            content=[{
                "type": "text",
                "text": text
            }],
            is_error=False
        )
    
    async def _handle_hello(self, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """Handle hello tool execution."""
        name = arguments.get("name", "World")
        
        if not isinstance(name, str):
            name = str(name) if name is not None else "World"
        
        # Fixed friendly response
        greeting = f"Hello, {name}! Welcome to the MCP Runtime Orchestrator. I'm here to help you execute tools and manage API connectors."
        
        return ToolExecutionResult(
            content=[{
                "type": "text",
                "text": greeting
            }],
            is_error=False
        )
    
    async def _handle_get_time(self, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """Handle get_time tool execution."""
        time_format = arguments.get("format", "iso").lower()
        
        now = datetime.datetime.now()
        
        if time_format == "iso":
            time_str = now.isoformat()
        elif time_format == "timestamp":
            time_str = str(int(now.timestamp()))
        elif time_format == "human":
            time_str = now.strftime("%A, %B %d, %Y at %I:%M:%S %p")
        else:
            raise ValueError(f"Invalid time format '{time_format}'. Use 'iso', 'timestamp', or 'human'")
        
        return ToolExecutionResult(
            content=[{
                "type": "text",
                "text": f"Current time ({time_format}): {time_str}"
            }],
            is_error=False
        )


# Global instance for use across the application
builtin_tool_handler = BuiltinToolHandler()
