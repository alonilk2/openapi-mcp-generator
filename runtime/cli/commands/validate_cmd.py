"""
MCP validate command implementation.

This command validates MCP connector manifests using the schema validation
that's already implemented in models.manifest.
"""

import sys
from pathlib import Path
from typing import List, Optional

import click
import yaml
from pydantic_core import ValidationError

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(parent_dir))

from models.manifest import ConnectorManifest


@click.command(
    name="validate",
    help="Validate MCP connector manifest files for syntax and schema compliance."
)
@click.argument(
    "manifest_files",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--strict", "-s",
    is_flag=True,
    help="Enable strict validation mode with additional checks."
)
@click.option(
    "--format", "-f",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format for validation results."
)
@click.pass_context
def validate_command(
    ctx: click.Context,
    manifest_files: tuple[Path, ...],
    strict: bool,
    format: str
) -> None:
    """
    Validate one or more MCP connector manifest files.
    
    This command performs comprehensive validation including:
    - YAML syntax validation
    - Schema compliance using Pydantic models
    - JSON Schema validation for tool schemas
    - Naming convention validation
    - Uniqueness constraints
    
    Exit codes:
    0 - All files valid
    1 - Validation errors found
    2 - System/file errors
    """
    verbose = ctx.obj.get('verbose', False)
    
    if verbose:
        click.echo(f"Validating {len(manifest_files)} manifest file(s) in {format} format...")
        if strict:
            click.echo("Strict validation mode enabled.")
    
    validation_results = []
    overall_success = True
    
    for manifest_file in manifest_files:
        result = validate_single_manifest(manifest_file, strict, verbose)
        validation_results.append(result)
        
        if not result["valid"]:
            overall_success = False
    
    # Output results based on format
    if format.lower() == "json":
        import json
        click.echo(json.dumps({
            "overall_valid": overall_success,
            "validated_count": len(manifest_files),
            "results": validation_results
        }, indent=2))
    else:
        output_text_results(validation_results, overall_success, verbose)
    
    # Exit with appropriate code
    sys.exit(0 if overall_success else 1)


def validate_single_manifest(manifest_file: Path, strict: bool, verbose: bool) -> dict:
    """
    Validate a single manifest file and return detailed results.
    
    Args:
        manifest_file: Path to the manifest file
        strict: Whether to enable strict validation
        verbose: Whether to include verbose details
        
    Returns:
        Dictionary with validation results
    """
    result = {
        "file": str(manifest_file),
        "valid": False,
        "errors": [],
        "warnings": [],
        "manifest": None
    }
    
    try:
        # Step 1: Load and parse YAML
        if verbose:
            click.echo(f"  Loading YAML file: {manifest_file}")
            
        with open(manifest_file, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)
        
        if not isinstance(yaml_data, dict):
            result["errors"].append("YAML file must contain a dictionary/object at root level")
            return result
        
        # Step 2: Validate against manifest schema
        if verbose:
            click.echo(f"  Validating manifest schema...")
            
        manifest = ConnectorManifest.from_yaml_dict(yaml_data)
        result["manifest"] = manifest.to_dict()
        
        # Step 3: Additional strict validation checks
        if strict:
            if verbose:
                click.echo(f"  Running strict validation checks...")
            strict_warnings = run_strict_validation(manifest)
            result["warnings"].extend(strict_warnings)
        
        result["valid"] = True
        
    except FileNotFoundError:
        result["errors"].append(f"File not found: {manifest_file}")
    except yaml.YAMLError as e:
        result["errors"].append(f"YAML parsing error: {str(e)}")
    except ValidationError as e:
        # Extract Pydantic validation errors
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            result["errors"].append(f"Validation error at {loc}: {msg}")
    except ValueError as e:
        result["errors"].append(f"Schema validation error: {str(e)}")
    except Exception as e:
        result["errors"].append(f"Unexpected error: {str(e)}")
    
    return result


def run_strict_validation(manifest: ConnectorManifest) -> List[str]:
    """
    Run additional strict validation checks and return warnings.
    
    Args:
        manifest: Validated ConnectorManifest instance
        
    Returns:
        List of warning messages
    """
    warnings = []
    
    # Check for descriptive tool names (not just single words)
    for tool in manifest.tools:
        if len(tool.name.split('_')) == 1 and len(tool.name) < 4:
            warnings.append(
                f"Tool '{tool.name}' has a very short name. "
                f"Consider a more descriptive name for clarity."
            )
    
    # Check for missing descriptions or very short descriptions
    for tool in manifest.tools:
        if len(tool.description) < 10:
            warnings.append(
                f"Tool '{tool.name}' has a very short description. "
                f"Consider adding more detail for better usability."
            )
    
    # Check for endpoint naming consistency
    endpoints = [tool.endpoint for tool in manifest.tools]
    prefixes = set()
    for endpoint in endpoints:
        if '.' in endpoint:
            prefix = endpoint.split('.')[0]
            prefixes.add(prefix)
    
    if len(prefixes) > 1:
        warnings.append(
            f"Multiple endpoint prefixes found: {sorted(prefixes)}. "
            f"Consider using consistent prefixes for related tools."
        )
    
    return warnings


def output_text_results(results: List[dict], overall_success: bool, verbose: bool) -> None:
    """Output validation results in human-readable text format."""
    
    total_files = len(results)
    valid_files = sum(1 for r in results if r["valid"])
    invalid_files = total_files - valid_files
    
    # Summary header
    click.echo(f"\n{'='*60}")
    click.echo(f"MCP Manifest Validation Results")
    click.echo(f"{'='*60}")
    click.echo(f"Total files: {total_files}")
    click.echo(f"Valid files: {click.style(str(valid_files), fg='green' if valid_files > 0 else 'yellow')}")
    click.echo(f"Invalid files: {click.style(str(invalid_files), fg='red' if invalid_files > 0 else 'green')}")
    
    # Detailed results per file
    for result in results:
        file_path = result["file"]
        is_valid = result["valid"]
        
        click.echo(f"\n{'-'*60}")
        status_color = "green" if is_valid else "red"
        status_text = "✓ VALID" if is_valid else "✗ INVALID"
        click.echo(f"File: {file_path}")
        click.echo(f"Status: {click.style(status_text, fg=status_color, bold=True)}")
        
        # Show errors
        if result["errors"]:
            click.echo(f"\nErrors ({len(result['errors'])}):")
            for i, error in enumerate(result["errors"], 1):
                click.echo(f"  {i}. {click.style(error, fg='red')}")
        
        # Show warnings  
        if result["warnings"]:
            click.echo(f"\nWarnings ({len(result['warnings'])}):")
            for i, warning in enumerate(result["warnings"], 1):
                click.echo(f"  {i}. {click.style(warning, fg='yellow')}")
        
        # Show manifest details if valid and verbose
        if is_valid and verbose and result["manifest"]:
            manifest_data = result["manifest"]
            click.echo(f"\nManifest Details:")
            click.echo(f"  Name: {manifest_data['name']}")
            click.echo(f"  Version: {manifest_data['version']}")
            click.echo(f"  Tools: {len(manifest_data['tools'])} defined")
            for tool in manifest_data['tools']:
                click.echo(f"    - {tool['name']} ({tool['endpoint']})")
    
    # Final summary
    click.echo(f"\n{'='*60}")
    if overall_success:
        click.echo(click.style("✓ All manifests are valid!", fg='green', bold=True))
    else:
        click.echo(click.style("✗ Some manifests have validation errors.", fg='red', bold=True))
        click.echo("Please fix the errors above and re-run validation.")