"""
Main CLI entry point for MCP commands.

This module provides the main click command group and entry point
for all MCP CLI operations.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

import click
from cli.commands.import_cmd import import_command
from cli.commands.validate_cmd import validate_command


@click.group(
    name="mcp",
    help="MCP platform CLI tools for connector development and management."
)
@click.version_option(version="0.2.0", prog_name="mcp")
@click.option(
    "--verbose", "-v", 
    is_flag=True, 
    help="Enable verbose logging output."
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """MCP CLI main command group."""
    # Store verbose flag in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose


# Register subcommands
cli.add_command(import_command)
cli.add_command(validate_command)

# Add credentials management command
from cli.commands.credentials_cmd import credentials
cli.add_command(credentials)


if __name__ == "__main__":
    cli()