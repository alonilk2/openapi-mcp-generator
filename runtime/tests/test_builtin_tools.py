"""
Test cases for built-in tool handlers.

This module tests the built-in tool system including tool discovery,
parameter validation, and execution results.
"""

import pytest
import datetime
from unittest.mock import patch

# Add the parent directory to the path for imports
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from core.builtin_tools import (
    BuiltinToolHandler,
    BuiltinTool,
    ToolParameter,
    ToolExecutionResult,
    builtin_tool_handler
)


class TestBuiltinToolHandler:
    """Test cases for the BuiltinToolHandler class."""
    
    def test_initialization(self):
        """Test that handler initializes with expected tools."""
        handler = BuiltinToolHandler()
        tools = handler.list_tools()
        
        assert len(tools) >= 3  # echo, hello, get_time
        tool_names = [tool.name for tool in tools]
        assert "echo" in tool_names
        assert "hello" in tool_names
        assert "get_time" in tool_names
    
    def test_has_tool(self):
        """Test tool existence checking."""
        handler = BuiltinToolHandler()
        
        assert handler.has_tool("echo")
        assert handler.has_tool("hello")
        assert handler.has_tool("get_time")
        assert not handler.has_tool("nonexistent_tool")
    
    def test_get_tool(self):
        """Test getting tool definitions."""
        handler = BuiltinToolHandler()
        
        echo_tool = handler.get_tool("echo")
        assert echo_tool.name == "echo"
        assert echo_tool.description
        assert len(echo_tool.parameters) == 1
        assert echo_tool.parameters[0].name == "text"
        assert echo_tool.parameters[0].required
        
        hello_tool = handler.get_tool("hello")
        assert hello_tool.name == "hello"
        assert hello_tool.description
        assert len(hello_tool.parameters) == 1
        assert hello_tool.parameters[0].name == "name"
        assert not hello_tool.parameters[0].required
        
        with pytest.raises(ValueError, match="Built-in tool 'nonexistent' not found"):
            handler.get_tool("nonexistent")
    
    @pytest.mark.asyncio
    async def test_echo_tool_execution(self):
        """Test echo tool execution."""
        handler = BuiltinToolHandler()
        
        # Test normal execution
        result = await handler.execute_tool("echo", {"text": "Hello, World!"})
        assert not result.is_error
        assert len(result.content) == 1
        assert result.content[0]["type"] == "text"
        assert result.content[0]["text"] == "Hello, World!"
        assert result.execution_time_ms >= 0
        
        # Test with empty text
        result = await handler.execute_tool("echo", {"text": ""})
        assert not result.is_error
        assert result.content[0]["text"] == ""
        
        # Test with missing text parameter
        result = await handler.execute_tool("echo", {})
        assert not result.is_error
        assert result.content[0]["text"] == ""
        
        # Test with invalid text type
        result = await handler.execute_tool("echo", {"text": 123})
        assert result.is_error
        assert "must be a string" in result.content[0]["text"]
    
    @pytest.mark.asyncio
    async def test_hello_tool_execution(self):
        """Test hello tool execution."""
        handler = BuiltinToolHandler()
        
        # Test with default name
        result = await handler.execute_tool("hello", {})
        assert not result.is_error
        assert len(result.content) == 1
        assert "Hello, World!" in result.content[0]["text"]
        assert "MCP Runtime Orchestrator" in result.content[0]["text"]
        
        # Test with custom name
        result = await handler.execute_tool("hello", {"name": "Alice"})
        assert not result.is_error
        assert "Hello, Alice!" in result.content[0]["text"]
        
        # Test with non-string name (should convert)
        result = await handler.execute_tool("hello", {"name": 42})
        assert not result.is_error
        assert "Hello, 42!" in result.content[0]["text"]
        
        # Test with None name
        result = await handler.execute_tool("hello", {"name": None})
        assert not result.is_error
        assert "Hello, World!" in result.content[0]["text"]
    
    @pytest.mark.asyncio
    async def test_get_time_tool_execution(self):
        """Test get_time tool execution."""
        handler = BuiltinToolHandler()
        
        # Test default ISO format
        result = await handler.execute_tool("get_time", {})
        assert not result.is_error
        assert "Current time (iso):" in result.content[0]["text"]
        
        # Test explicit ISO format
        result = await handler.execute_tool("get_time", {"format": "iso"})
        assert not result.is_error
        assert "Current time (iso):" in result.content[0]["text"]
        
        # Test timestamp format
        result = await handler.execute_tool("get_time", {"format": "timestamp"})
        assert not result.is_error
        assert "Current time (timestamp):" in result.content[0]["text"]
        # Should be a numeric timestamp
        timestamp_part = result.content[0]["text"].split(": ")[1]
        assert timestamp_part.isdigit()
        
        # Test human format
        result = await handler.execute_tool("get_time", {"format": "human"})
        assert not result.is_error
        assert "Current time (human):" in result.content[0]["text"]
        # Should contain day names and AM/PM
        text = result.content[0]["text"]
        assert any(day in text for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
        assert ("AM" in text or "PM" in text)
        
        # Test invalid format
        result = await handler.execute_tool("get_time", {"format": "invalid"})
        assert result.is_error
        assert "Invalid time format" in result.content[0]["text"]
    
    @pytest.mark.asyncio
    async def test_nonexistent_tool_execution(self):
        """Test execution of non-existent tool."""
        handler = BuiltinToolHandler()
        
        result = await handler.execute_tool("nonexistent", {})
        assert result.is_error
        assert "not found" in result.content[0]["text"]
        assert result.execution_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_execution_timing(self):
        """Test that execution time is properly measured."""
        handler = BuiltinToolHandler()
        
        # Mock datetime to control timing
        mock_times = [
            datetime.datetime(2023, 1, 1, 12, 0, 0, 0),      # start
            datetime.datetime(2023, 1, 1, 12, 0, 0, 50000)  # end (50ms later)
        ]
        
        with patch('core.builtin_tools.datetime') as mock_datetime:
            mock_datetime.datetime.now.side_effect = mock_times
            # Also need to patch for the actual time formatting in get_time
            mock_datetime.datetime.side_effect = lambda *args, **kwargs: datetime.datetime(*args, **kwargs)
            
            result = await handler.execute_tool("echo", {"text": "test"})
            assert result.execution_time_ms == 50
    
    def test_global_instance(self):
        """Test that global instance is available and functional."""
        assert builtin_tool_handler is not None
        assert isinstance(builtin_tool_handler, BuiltinToolHandler)
        assert builtin_tool_handler.has_tool("echo")
        assert builtin_tool_handler.has_tool("hello")
        assert builtin_tool_handler.has_tool("get_time")


class TestToolModels:
    """Test cases for tool data models."""
    
    def test_tool_parameter_model(self):
        """Test ToolParameter model."""
        param = ToolParameter(
            name="test_param",
            type="string",
            description="A test parameter",
            required=True,
            default="default_value"
        )
        
        assert param.name == "test_param"
        assert param.type == "string"
        assert param.description == "A test parameter"
        assert param.required
        assert param.default == "default_value"
        
        # Test with defaults
        param2 = ToolParameter(
            name="param2",
            type="number",
            description="Another param"
        )
        assert param2.required  # Default is True
        assert param2.default is None  # Default is None
    
    def test_builtin_tool_model(self):
        """Test BuiltinTool model."""
        params = [
            ToolParameter(name="param1", type="string", description="First param"),
            ToolParameter(name="param2", type="number", description="Second param", required=False)
        ]
        
        tool = BuiltinTool(
            name="test_tool",
            description="A test tool",
            parameters=params,
            category="test"
        )
        
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert len(tool.parameters) == 2
        assert tool.category == "test"
        
        # Test with default category
        tool2 = BuiltinTool(
            name="tool2",
            description="Another tool",
            parameters=[]
        )
        assert tool2.category == "builtin"
    
    def test_tool_execution_result_model(self):
        """Test ToolExecutionResult model."""
        content = [{"type": "text", "text": "Test result"}]
        
        result = ToolExecutionResult(
            content=content,
            is_error=False,
            execution_time_ms=100
        )
        
        assert result.content == content
        assert not result.is_error
        assert result.execution_time_ms == 100
        
        # Test with defaults
        result2 = ToolExecutionResult(content=content)
        assert not result2.is_error  # Default is False
        assert result2.execution_time_ms == 0  # Default is 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
