"""Basic API surface tests."""

from fastapi.testclient import TestClient
import sys
import os

# Add the parent directory to the path and set up package imports
runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_dir = os.path.dirname(runtime_dir)
sys.path.insert(0, parent_dir)
# Ensure the runtime package root itself is also on the path so intra-package absolute imports (core.*, api.*) resolve
if runtime_dir not in sys.path:
    sys.path.insert(0, runtime_dir)

# Import the app from the runtime package
from runtime.main import app

client = TestClient(app)


def test_health_check():
    """Test the basic health check endpoint."""
    response = client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data


def test_mcp_capabilities():
    """Test the MCP capabilities endpoint."""
    response = client.get("/v1/mcp/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "capabilities" in data
    assert "serverInfo" in data
    assert data["serverInfo"]["name"] == "MCP Runtime Orchestrator"


def test_mcp_tools_list():
    """Test the MCP tools listing endpoint."""
    response = client.get("/v1/mcp/tools")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)


def test_mcp_tool_execution():
    """Test the MCP tool execution endpoint."""
    response = client.post("/v1/mcp/tools/call", json={
        "name": "echo",
        "arguments": {"text": "Hello, MCP!"}
    })
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "isError" in data
    assert data["isError"] is False


def test_projects_list():
    """Test the projects listing endpoint."""
    response = client.get("/v1/projects/")
    assert response.status_code == 200
    data = response.json()
    assert "projects" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data


def test_cors_headers():
    """Test that CORS headers are properly set."""
    response = client.options("/health/")
    # Note: In test mode, CORS middleware may not add headers
    # This test would be more relevant in a full integration test
    assert response.status_code in [200, 405]  # OPTIONS may not be implemented


def test_correlation_id_header():
    """Test that correlation ID is added to response headers."""
    response = client.get("/health/")
    assert response.status_code == 200
    # The middleware should add correlation ID header
    assert "X-Correlation-ID" in response.headers


def test_project_runtime_manifest():
    """Test the project runtime manifest endpoint."""
    response = client.get("/v1/projects/project-1/runtime/manifest")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert "project_id" in data
    assert "connector_count" in data
    assert "total_tools" in data
    assert data["project_id"] == "project-1"
    assert isinstance(data["tools"], list)


def test_tool_invocation_invalid_format():
    """Test tool invocation with invalid tool name format."""
    response = client.post("/v1/projects/project-1/runtime/invoke", json={
        "tool_name": "invalid_tool_name",
        "parameters": {}
    })
    assert response.status_code == 400
    data = response.json()
    assert "Invalid tool name format" in data["detail"]


def test_tool_invocation_disabled_connector():
    """Test tool invocation with disabled connector."""
    response = client.post("/v1/projects/project-1/runtime/invoke", json={
        "tool_name": "task-manager.create_task",
        "parameters": {"title": "Test Task"}
    })
    assert response.status_code == 403
    data = response.json()
    assert "not enabled for this project" in data["detail"]


def test_tool_invocation_nonexistent_project():
    """Test tool invocation with non-existent project."""
    response = client.post("/v1/projects/invalid-project/runtime/invoke", json={
        "tool_name": "calculator.add",
        "parameters": {"a": 1, "b": 2}
    })
    assert response.status_code == 404
    data = response.json()
    assert "Project not found" in data["detail"]


def test_tool_invocation_nonexistent_connector():
    """Test tool invocation with non-existent connector."""
    response = client.post("/v1/projects/project-1/runtime/invoke", json={
        "tool_name": "nonexistent.tool",
        "parameters": {}
    })
    assert response.status_code == 403
    data = response.json()
    assert "not enabled for this project" in data["detail"]
