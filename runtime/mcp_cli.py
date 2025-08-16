#!/usr/bin/env python3
"""
MCP CLI Entry Point Script

This script provides the main entry point for MCP CLI commands.
It can be run directly or installed as a package command.

Usage:
    python mcp_cli.py --help
    python mcp_cli.py import <openapi_spec> [options]
    python mcp_cli.py validate <manifest_file> [options]
"""

import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from cli.main import cli

if __name__ == "__main__":
    cli()