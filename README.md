# MCP Runtime Orchestrator

The Runtime Orchestrator is a FastAPI-based service that acts as an MCP (Model Context Protocol) gateway. It loads connectors dynamically, handles tool calls with built-in authentication, retries, rate limiting, and provides comprehensive observability.

## Demo
![MCP CLI Import Demo](./assets/mcp_cli_import_demo.gif)
![Usage Demo](./assets/usage_demo.gif)

## Features

- **MCP Gateway**: Implements core MCP capabilities (capabilities, tool discovery & execution)
- **Connector Execution**: Execution path for all connector tools through an authenticated client (In development)
- **Dynamic Connector Loading**: Hot-swappable connectors from manifests with optional hot-reload
- **Built-in Security (Still in development)**: Credential resolution for API Key & OAuth2 client credentials (JWT / RBAC planned)
- **Development Tools**: Hot reload, sample connector auto-install

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Runtime Orchestrator                 │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Application Layer                                  │
│  ├── Health Endpoints        ├── MCP Protocol Endpoints     │
│  ├── Project Management      ├── Runtime Control           │
│  └── WebSocket Streaming     └── Authentication            │
└──────────────────────────────────────────────────────────────┤

```

## Quick Start

### CLI Setup

1. **Clone and setup environment**:

   ```powershell
   cd runtime
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1  # Windows PowerShell
   pip install -r requirements.txt
   ```

2. **Configure environment**:

   ```powershell
   $env:MCP_RUNTIME_ENVIRONMENT = 'development'
   $env:MCP_RUNTIME_HOT_RELOAD = 'true'
   ```

3. **Import your first connector**:

   ```powershell
   # Import a public API (example: JSONPlaceholder)
   python mcp_cli.py import https://jsonplaceholder.typicode.com/openapi.json --name "json-placeholder"
   
   # Validate the generated manifest
   python mcp_cli.py validate samples/json_placeholder.yaml --strict
   ```

4. **Set up credentials (if needed)**:

   ```powershell
   # For APIs requiring API keys
   python mcp_cli.py credentials store json-placeholder --auth-type api_key --api-key "your-api-key"
   ```

#### VS Code MCP Configuration

To use the MCP Runtime Orchestrator with VS Code, add the following configuration to your `mcp.json` file:

```jsonc
{
  "servers": {
    "[api-name]": {
      "type": "stdio",
      "command": "python",
      "args": [
        "/runtime/mcp_stdio_server.py"
      ]
    },
  },
  "inputs": []
}
```

**Configuration Workflow:**

1. **Locate your MCP configuration file**:
   - On Windows: `%APPDATA%\Code\User\mcp.json`
   - On macOS: `~/Library/Application Support/Code/User/mcp.json`
   - On Linux: `~/.config/Code/User/mcp.json`

2. **Add the servers configuration**:
   - **Local MCP Runtime**: Configure the `[api-name]` server to use the stdio server with the full path to `mcp_stdio_server.py`

3. **Restart VS Code** to load the new MCP configuration

4. **Verify connection** by checking that tools from both servers are available in the MCP tools panel


## CLI Commands and Workflows

The MCP Runtime Orchestrator provides several CLI interfaces for managing connectors and credentials:

### MCP CLI (`mcp_cli.py`)

The main CLI entry point provides comprehensive connector management capabilities:

#### Import Command - Convert OpenAPI to MCP Connectors

![MCP CLI Import Demo](./assets/mcp_cli_import_demo.gif)

```powershell
# Import from URL
python mcp_cli.py import https://api.example.com/openapi.json

# Import from local file with customization
python mcp_cli.py import ./my-api.yaml --name "@myorg/my-api" --output my-connector.yaml

# Filter specific paths and limit tools
python mcp_cli.py import spec.json --include-path "/users/*" --exclude-path "/admin/*" --max-tools 25

# Force overwrite and validate
python mcp_cli.py import spec.json --force --validate
```

**Key Features:**

- Supports JSON/YAML OpenAPI specifications from files, URLs, or stdin
- Automatically resolves $ref references and validates OpenAPI specs
- Converts operations to MCP tools with proper parameter mapping
- Intelligent endpoint naming and base URL inference
- Saves generated manifests to `samples/` directory by default

#### Validate Command - Verify Connector Manifests

```powershell
# Validate single manifest
python mcp_cli.py validate my-connector.yaml

# Validate multiple manifests with strict checks
python mcp_cli.py validate samples/*.yaml --strict

# JSON output for automation
python mcp_cli.py validate connector.yaml --format json
```

**Validation Checks:**

- YAML syntax validation
- Schema compliance using Pydantic models
- JSON Schema validation for tool input/output schemas
- Naming convention enforcement
- Tool uniqueness constraints
- Strict mode: descriptive naming, endpoint consistency

#### Credentials Management

```powershell
# Store API key credentials
python mcp_cli.py credentials store my-connector --auth-type api_key --api-key "sk-123..." --key-name "Authorization" --scheme "Bearer"

# Store OAuth2 client credentials
python mcp_cli.py credentials store oauth-api --auth-type oauth2_client_credentials --client-id "client123" --client-secret "secret456" --token-url "https://api.oauth.com/token"

# List stored credentials
python mcp_cli.py credentials list --format table
python mcp_cli.py credentials list --connector-name my-connector

# Show detailed credentials
python mcp_cli.py credentials show my-connector --format yaml

# Delete credentials
python mcp_cli.py credentials delete my-connector --force
```

### MCP Stdio Server (`mcp_stdio_server.py`)

The stdio server provides MCP protocol compliance for integration with VS Code and other MCP clients:

```powershell
# Start stdio server (for MCP client integration)
python mcp_stdio_server.py

# With verbose logging to stderr
MCP_RUNTIME_DEBUG=true python mcp_stdio_server.py
```

**Protocol Support:**

- `initialize` - Server capability negotiation
- `tools/list` - Dynamic tool discovery with hot-reload
- `tools/call` - Authenticated tool execution
- Built-in tools (echo, hello, get_time) + connector-derived tools

### Development Workflows

#### 1. Creating a New Connector

```powershell
# Step 1: Import OpenAPI spec
python mcp_cli.py import https://api.stripe.com/openapi.yaml --name "@stripe/payments" --max-tools 20

# Step 2: Validate the generated manifest
python mcp_cli.py validate samples/stripe_payments.yaml --strict

# Step 3: Store authentication credentials
python mcp_cli.py credentials store "@stripe/payments" --auth-type api_key --api-key "sk_test_..." --scheme "Bearer"

# Step 4: Test with runtime (hot-reload will pick up the new manifest)
MCP_RUNTIME_HOT_RELOAD=true python main.py
```

#### 2. Managing Existing Connectors

```powershell
# List all stored credentials
python mcp_cli.py credentials list --format table

# Update credentials for a connector
python mcp_cli.py credentials delete old-connector
python mcp_cli.py credentials store old-connector --auth-type api_key --api-key "new-key"

# Re-validate after manifest changes
python mcp_cli.py validate samples/*.yaml --strict --verbose
```

## Configuration

The runtime uses environment variables with the `MCP_RUNTIME_` prefix. Key settings:

```bash
# Server Configuration
MCP_RUNTIME_HOST=0.0.0.0
MCP_RUNTIME_PORT=8000
MCP_RUNTIME_ENVIRONMENT=development

# Security
MCP_RUNTIME_JWT_SECRET_KEY=your-secret-key
MCP_RUNTIME_ALLOWED_HOSTS=["*"]

# Database
MCP_RUNTIME_DATABASE_URL=postgresql://user:pass@host:5432/db

# Runtime Settings
MCP_RUNTIME_MAX_CONCURRENT_CONNECTORS=100
MCP_RUNTIME_CONNECTOR_TIMEOUT_SECONDS=30
```

See `.env.example` for complete configuration options.

## Development

### Project Structure

```bash
runtime/
├── main.py              # FastAPI application entry point
├── mcp_cli.py          # Main CLI entry point
├── mcp_stdio_server.py # MCP stdio server entry point
├── cli/                # CLI command modules
│   ├── main.py         # CLI command group setup
│   └── commands/       # Individual CLI commands
│       ├── import_cmd.py     # OpenAPI import command
│       ├── validate_cmd.py   # Manifest validation command
│       └── credentials_cmd.py # Credential management
├── core/               # Core functionality
│   ├── config.py       # Configuration management
│   ├── builtin_tools.py # Built-in tool implementations
│   ├── registry.py     # Connector registry system
│   └── authenticated_client.py # Tool execution client
├── models/             # Pydantic models
│   └── manifest.py     # Connector manifest models
├── samples/            # Sample connector manifests
└── tests/              # Test suite
```

### Example CLI Workflow

```powershell
# Import connector from OpenAPI spec
python mcp_cli.py import https://petstore.swagger.io/v2/swagger.json --name "petstore" --max-tools 10

# Validate the manifest
python mcp_cli.py validate samples/petstore.yaml --strict --verbose

# Store API credentials
python mcp_cli.py credentials store petstore --auth-type api_key --api-key "special-key" --location header

# List generated tools and credentials
python mcp_cli.py credentials list --connector-name petstore

# Start stdio server for MCP client integration
python mcp_stdio_server.py
```

### MCP Client JSON-RPC Examples

When connected via stdio server:

```json
# Get server capabilities
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}

# List available tools
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

# Execute a tool
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "Hello MCP!"}}}
```

## License

MIT License - see LICENSE file for details.
