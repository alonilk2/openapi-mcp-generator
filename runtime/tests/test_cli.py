"""
Tests for MCP CLI commands - Phase 0-2

This module tests the CLI commands for importing and validating MCP connector manifests.
"""

import sys
from pathlib import Path
import tempfile
import json
import yaml
import pytest
from typing import Dict, Any
from click.testing import CliRunner

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from cli.main import cli
from cli.commands.validate_cmd import validate_command
from cli.commands.import_cmd import import_command
from models.manifest import ConnectorManifest


class TestValidateCommand:
    """Test the MCP validate command."""
    
    def test_validate_valid_manifest(self):
        """Test validation of a valid manifest file."""
        runner = CliRunner()
        
        # Use existing valid manifest
        manifest_path = parent_dir / "samples" / "calculator.yaml"
        result = runner.invoke(cli, ["validate", str(manifest_path)])
        
        assert result.exit_code == 0
        assert "✓ VALID" in result.output
        assert "All manifests are valid!" in result.output
    
    def test_validate_multiple_manifests(self):
        """Test validation of multiple manifest files."""
        runner = CliRunner()
        
        manifest1 = parent_dir / "samples" / "calculator.yaml"
        manifest2 = parent_dir / "samples" / "weather-api.yaml"
        
        result = runner.invoke(cli, ["validate", str(manifest1), str(manifest2)])
        
        assert result.exit_code == 0
        assert "Total files: 2" in result.output
        assert "Valid files: 2" in result.output
        assert "Invalid files: 0" in result.output
    
    def test_validate_strict_mode(self):
        """Test validation with strict mode."""
        runner = CliRunner()
        
        manifest_path = parent_dir / "samples" / "calculator.yaml"
        result = runner.invoke(cli, ["validate", "--strict", str(manifest_path)])
        
        assert result.exit_code == 0
        # Should still pass but might have warnings
    
    def test_validate_json_output(self):
        """Test validation with JSON output format."""
        runner = CliRunner()
        
        manifest_path = parent_dir / "samples" / "calculator.yaml"
        result = runner.invoke(cli, ["validate", "--format", "json", str(manifest_path)])
        
        assert result.exit_code == 0
        
        # Parse JSON output
        output_data = json.loads(result.output)
        assert output_data["overall_valid"] is True
        assert output_data["validated_count"] == 1
        assert len(output_data["results"]) == 1
    
    def test_validate_invalid_manifest(self):
        """Test validation of an invalid manifest."""
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            # Create invalid manifest
            invalid_manifest = {
                "connector": {
                    "name": "invalid-name-with-@-in-wrong-place@",  # Invalid name
                    "version": "not-semver",  # Invalid version
                    "tools": []  # Empty tools array (invalid)
                }
            }
            yaml.dump(invalid_manifest, f)
            f.flush()
            
            result = runner.invoke(cli, ["validate", f.name])
            
            assert result.exit_code == 1
            assert "✗ INVALID" in result.output
            assert "Validation error" in result.output
    
    def test_validate_nonexistent_file(self):
        """Test validation of nonexistent file."""
        runner = CliRunner()
        
        result = runner.invoke(cli, ["validate", "/nonexistent/file.yaml"])
        
        assert result.exit_code == 1
        assert "File not found" in result.output


class TestImportCommand:
    """Test the MCP import command."""
    
    def create_test_openapi_spec(self) -> Dict[str, Any]:
        """Create a test OpenAPI specification."""
        return {
            "openapi": "3.0.1",
            "info": {
                "title": "Test API",
                "description": "A test API for validation",
                "version": "1.0.0"
            },
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "summary": "List all items",
                        "responses": {
                            "200": {
                                "description": "List of items",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "name": {"type": "string"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "post": {
                        "operationId": "createItem",
                        "summary": "Create new item",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["name"]
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "description": "Created item",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "id": {"type": "integer"},
                                                "name": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def test_import_valid_openapi_file(self):
        """Test importing a valid OpenAPI file."""
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.create_test_openapi_spec(), f)
            f.flush()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "test-connector.yaml"
                
                result = runner.invoke(cli, [
                    "import",
                    f.name,
                    "--output", str(output_path),
                    "--validate"
                ])
                
                assert result.exit_code == 0
                assert "Successfully generated MCP connector manifest" in result.output
                assert "Tools generated: 2" in result.output
                
                # Check that output file was created
                assert output_path.exists()
                
                # Validate the generated manifest
                with open(output_path, 'r') as manifest_file:
                    manifest_data = yaml.safe_load(manifest_file)
                    manifest = ConnectorManifest.from_yaml_dict(manifest_data)
                    assert len(manifest.tools) == 2
                    assert manifest.name == "test-api"
                    assert manifest.version == "1.0.0"
    
    def test_import_with_name_override(self):
        """Test importing with custom name and version."""
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.create_test_openapi_spec(), f)
            f.flush()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "custom-connector.yaml"
                
                result = runner.invoke(cli, [
                    "import",
                    f.name,
                    "--output", str(output_path),
                    "--name", "@myorg/custom-api",
                    "--version", "2.1.0",
                    "--validate"
                ])
                
                assert result.exit_code == 0
                
                # Check generated manifest has custom values
                with open(output_path, 'r') as manifest_file:
                    manifest_data = yaml.safe_load(manifest_file)
                    manifest = ConnectorManifest.from_yaml_dict(manifest_data)
                    assert manifest.name == "@myorg/custom-api"
                    assert manifest.version == "2.1.0"
    
    def test_import_with_path_filters(self):
        """Test importing with path include/exclude filters."""
        runner = CliRunner()
        
        # Create OpenAPI spec with multiple paths
        spec = self.create_test_openapi_spec()
        spec["paths"]["/admin/users"] = {
            "get": {
                "operationId": "getAdminUsers",
                "summary": "Get admin users",
                "responses": {
                    "200": {
                        "description": "Admin users",
                        "content": {
                            "application/json": {
                                "schema": {"type": "array"}
                            }
                        }
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(spec, f)
            f.flush()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "filtered-connector.yaml"
                
                result = runner.invoke(cli, [
                    "import",
                    f.name,
                    "--output", str(output_path),
                    "--exclude-path", "/admin/*",
                    "--validate"
                ])
                
                assert result.exit_code == 0
                
                # Check that admin paths were excluded
                with open(output_path, 'r') as manifest_file:
                    manifest_data = yaml.safe_load(manifest_file)
                    manifest = ConnectorManifest.from_yaml_dict(manifest_data)
                    tool_names = [tool.name for tool in manifest.tools]
                    assert "get_admin_users" not in tool_names
                    assert "list_items" in tool_names
                    assert "create_item" in tool_names
    
    def test_import_invalid_openapi(self):
        """Test importing an invalid OpenAPI specification."""
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            # Create invalid OpenAPI spec
            invalid_spec = {
                "openapi": "3.0.1",
                # Missing required 'info' field
                "paths": {}
            }
            json.dump(invalid_spec, f)
            f.flush()
            
            result = runner.invoke(cli, ["import", f.name])
            
            assert result.exit_code == 1
            assert "Import failed" in result.output
    
    def test_import_auto_generated_filename(self):
        """Test import with auto-generated output filename."""
        runner = CliRunner()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.create_test_openapi_spec(), f)
            f.flush()
            
            # Run in temp directory to control output location
            with tempfile.TemporaryDirectory() as tmpdir:
                import os
                original_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    
                    result = runner.invoke(cli, ["import", f.name, "--validate"])
                    
                    assert result.exit_code == 0
                    assert "Successfully generated MCP connector manifest" in result.output
                    
                    # Check that file was created with expected name
                    expected_file = Path(tmpdir) / "test-api.yaml"
                    assert expected_file.exists()
                    
                finally:
                    os.chdir(original_cwd)


class TestCLIIntegration:
    """Test CLI integration and end-to-end workflows."""
    
    def test_cli_main_help(self):
        """Test main CLI help command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        
        assert result.exit_code == 0
        assert "MCP platform CLI tools" in result.output
        assert "import" in result.output
        assert "validate" in result.output
    
    def test_cli_version(self):
        """Test CLI version command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        
        assert result.exit_code == 0
        assert "0.2.0" in result.output
    
    def test_end_to_end_import_and_validate(self):
        """Test complete workflow: import OpenAPI then validate result."""
        runner = CliRunner()
        
        # Create test OpenAPI spec
        test_spec = {
            "openapi": "3.0.1",
            "info": {
                "title": "E2E Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/test": {
                    "get": {
                        "operationId": "testOperation",
                        "summary": "Test operation",
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "message": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as spec_file:
            json.dump(test_spec, spec_file)
            spec_file.flush()
            
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / "e2e-test.yaml"
                
                # Step 1: Import
                import_result = runner.invoke(cli, [
                    "import",
                    spec_file.name,
                    "--output", str(output_path),
                    "--validate"
                ])
                
                assert import_result.exit_code == 0
                assert output_path.exists()
                
                # Step 2: Validate with strict mode
                validate_result = runner.invoke(cli, [
                    "validate",
                    "--strict",
                    "--format", "json",
                    str(output_path)
                ])
                
                assert validate_result.exit_code == 0
                
                # Parse validation results
                validation_data = json.loads(validate_result.output)
                assert validation_data["overall_valid"] is True
                assert validation_data["validated_count"] == 1
                
                result = validation_data["results"][0]
                assert result["valid"] is True
                assert result["manifest"]["name"] == "e2e-test-api"
                assert len(result["manifest"]["tools"]) == 1
                assert result["manifest"]["tools"][0]["name"] == "test_operation"