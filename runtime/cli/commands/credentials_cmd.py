"""
CLI commands for managing connector credentials.

This module provides command-line interface for storing, listing, and managing
authentication credentials for MCP connectors.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

import click
import yaml

# Add the parent directory to the path for package imports
runtime_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(runtime_dir))

from core.secret_factory import get_secret_storage, close_secret_storage
from core.secrets import SecretType, SecretNotFoundError, SecretStorageError, generate_secret_name


@click.group()
def credentials():
    """Manage connector credentials."""
    pass


@credentials.command()
@click.argument('connector_name')
@click.option('--auth-type', 
              type=click.Choice(['api_key', 'oauth2_client_credentials']),
              required=True,
              help='Type of authentication')
@click.option('--api-key', 
              help='API key value (for api_key auth type)')
@click.option('--key-name', 
              default='authorization',
              help='API key parameter name (for api_key auth type)')
@click.option('--location', 
              type=click.Choice(['header', 'query', 'cookie']),
              default='header',
              help='Where to place API key (for api_key auth type)')
@click.option('--scheme', 
              help='Authentication scheme like "Bearer" (for api_key auth type)')
@click.option('--client-id', 
              help='OAuth2 client ID (for oauth2_client_credentials auth type)')
@click.option('--client-secret', 
              help='OAuth2 client secret (for oauth2_client_credentials auth type)')
@click.option('--token-url', 
              help='OAuth2 token URL (for oauth2_client_credentials auth type)')
@click.option('--scopes', 
              help='OAuth2 scopes (comma-separated, for oauth2_client_credentials auth type)')
@click.option('--description', 
              help='Description for the credentials')
@click.option('--expires-at', 
              help='Expiration date (ISO 8601 format)')
@click.option('--tag', 
              multiple=True,
              help='Tag in format key=value (can be used multiple times)')
def store(connector_name: str, auth_type: str, **kwargs):
    """Store credentials for a connector."""
    
    async def _store_credentials():
        try:
            storage = await get_secret_storage()
            
            # Parse tags
            tags = {}
            for tag in kwargs.get('tag', []):
                if '=' not in tag:
                    click.echo(f"Error: Invalid tag format '{tag}'. Use key=value format.", err=True)
                    return 1
                key, value = tag.split('=', 1)
                tags[key] = value
            
            if auth_type == 'api_key':
                if not kwargs.get('api_key'):
                    click.echo("Error: --api-key is required for api_key auth type", err=True)
                    return 1
                
                # Store API key
                secret_name = generate_secret_name(connector_name, SecretType.API_KEY)
                secret_tags = {
                    **tags,
                    "key_name": kwargs.get('key_name', 'authorization'),
                    "location": kwargs.get('location', 'header'),
                    "scheme": kwargs.get('scheme', '')
                }
                
                await storage.store_secret(
                    name=secret_name,
                    value=kwargs['api_key'],
                    secret_type=SecretType.API_KEY,
                    connector_name=connector_name,
                    description=kwargs.get('description'),
                    tags=secret_tags,
                    expires_at=kwargs.get('expires_at')
                )
                
                click.echo(f"✓ Stored API key credentials for connector '{connector_name}'")
                
            elif auth_type == 'oauth2_client_credentials':
                if not kwargs.get('client_id') or not kwargs.get('client_secret'):
                    click.echo("Error: --client-id and --client-secret are required for oauth2_client_credentials auth type", err=True)
                    return 1
                
                # Store OAuth2 credentials
                client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
                client_secret_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_SECRET)
                
                base_tags = {
                    **tags,
                    "token_url": kwargs.get('token_url', ''),
                    "scopes": kwargs.get('scopes', '')
                }
                
                # Store client ID
                await storage.store_secret(
                    name=client_id_name,
                    value=kwargs['client_id'],
                    secret_type=SecretType.OAUTH2_CLIENT_ID,
                    connector_name=connector_name,
                    description=f"OAuth2 Client ID - {kwargs.get('description', '')}".strip(),
                    tags=base_tags,
                    expires_at=kwargs.get('expires_at')
                )
                
                # Store client secret
                await storage.store_secret(
                    name=client_secret_name,
                    value=kwargs['client_secret'],
                    secret_type=SecretType.OAUTH2_CLIENT_SECRET,
                    connector_name=connector_name,
                    description=f"OAuth2 Client Secret - {kwargs.get('description', '')}".strip(),
                    tags=base_tags,
                    expires_at=kwargs.get('expires_at')
                )
                
                click.echo(f"✓ Stored OAuth2 credentials for connector '{connector_name}'")
            
            await close_secret_storage()
            return 0
            
        except SecretStorageError as e:
            click.echo(f"Error storing credentials: {e}", err=True)
            return 1
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            return 1
    
    sys.exit(asyncio.run(_store_credentials()))


@credentials.command("list")
@click.option('--connector-name', 
              help='Filter by connector name')
@click.option('--auth-type', 
              type=click.Choice(['api_key', 'oauth2_client_credentials']),
              help='Filter by auth type')
@click.option('--format', 
              type=click.Choice(['table', 'json', 'yaml']),
              default='table',
              help='Output format')
def list_creds(connector_name: Optional[str], auth_type: Optional[str], format: str):
    """List stored credentials."""
    
    async def _list_credentials():
        try:
            storage = await get_secret_storage()
            
            # Convert auth_type to SecretType for filtering
            secret_type_filter = None
            if auth_type:
                if auth_type == "api_key":
                    secret_type_filter = SecretType.API_KEY
                elif auth_type == "oauth2_client_credentials":
                    secret_type_filter = SecretType.OAUTH2_CLIENT_ID
            
            secrets = await storage.list_secrets(
                connector_name=connector_name,
                secret_type=secret_type_filter
            )
            
            # Group OAuth2 credentials by connector
            credentials_map = {}
            
            for secret in secrets:
                if secret.secret_type == SecretType.API_KEY:
                    credentials_map[secret.connector_name] = {
                        "connector_name": secret.connector_name,
                        "auth_type": "api_key",
                        "description": secret.description,
                        "expires_at": secret.expires_at,
                        "tags": {k: v for k, v in secret.tags.items() if k not in ["key_name", "location", "scheme"]},
                        "config": {
                            "key_name": secret.tags.get("key_name", ""),
                            "location": secret.tags.get("location", "header"),
                            "scheme": secret.tags.get("scheme", "")
                        }
                    }
                elif secret.secret_type == SecretType.OAUTH2_CLIENT_ID:
                    credentials_map[secret.connector_name] = {
                        "connector_name": secret.connector_name,
                        "auth_type": "oauth2_client_credentials",
                        "description": secret.description,
                        "expires_at": secret.expires_at,
                        "tags": {k: v for k, v in secret.tags.items() if k not in ["token_url", "scopes"]},
                        "config": {
                            "token_url": secret.tags.get("token_url", ""),
                            "scopes": secret.tags.get("scopes", "").split(",") if secret.tags.get("scopes") else []
                        }
                    }
            
            credentials_list = list(credentials_map.values())
            
            if format == "json":
                click.echo(json.dumps(credentials_list, indent=2))
            elif format == "yaml":
                click.echo(yaml.dump(credentials_list, default_flow_style=False))
            else:  # table format
                if not credentials_list:
                    click.echo("No credentials found.")
                    return 0
                
                # Print table header
                click.echo(f"{'Connector':<25} {'Auth Type':<20} {'Description':<30} {'Expires':<20}")
                click.echo("-" * 95)
                
                # Print table rows
                for cred in credentials_list:
                    connector = cred['connector_name'][:24]
                    auth = cred['auth_type'][:19]
                    desc = (cred['description'] or '')[:29]
                    expires = (cred['expires_at'] or 'Never')[:19]
                    
                    click.echo(f"{connector:<25} {auth:<20} {desc:<30} {expires:<20}")
            
            await close_secret_storage()
            return 0
            
        except SecretStorageError as e:
            click.echo(f"Error listing credentials: {e}", err=True)
            return 1
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            return 1
    
    sys.exit(asyncio.run(_list_credentials()))


@credentials.command()
@click.argument('connector_name')
@click.option('--format', 
              type=click.Choice(['table', 'json', 'yaml']),
              default='table',
              help='Output format')
def show(connector_name: str, format: str):
    """Show details for specific connector credentials."""
    
    async def _show_credentials():
        try:
            storage = await get_secret_storage()
            
            # Try to find credentials for the connector
            api_key_name = generate_secret_name(connector_name, SecretType.API_KEY)
            oauth_client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
            
            credential_info = None
            
            if await storage.secret_exists(api_key_name):
                secret_value = await storage.get_secret(api_key_name)
                credential_info = {
                    "connector_name": secret_value.metadata.connector_name,
                    "auth_type": "api_key",
                    "description": secret_value.metadata.description,
                    "expires_at": secret_value.metadata.expires_at,
                    "tags": {k: v for k, v in secret_value.metadata.tags.items() if k not in ["key_name", "location", "scheme"]},
                    "config": {
                        "key_name": secret_value.metadata.tags.get("key_name", ""),
                        "location": secret_value.metadata.tags.get("location", "header"),
                        "scheme": secret_value.metadata.tags.get("scheme", "")
                    }
                }
            elif await storage.secret_exists(oauth_client_id_name):
                secret_value = await storage.get_secret(oauth_client_id_name)
                credential_info = {
                    "connector_name": secret_value.metadata.connector_name,
                    "auth_type": "oauth2_client_credentials",
                    "description": secret_value.metadata.description,
                    "expires_at": secret_value.metadata.expires_at,
                    "tags": {k: v for k, v in secret_value.metadata.tags.items() if k not in ["token_url", "scopes"]},
                    "config": {
                        "token_url": secret_value.metadata.tags.get("token_url", ""),
                        "scopes": secret_value.metadata.tags.get("scopes", "").split(",") if secret_value.metadata.tags.get("scopes") else []
                    }
                }
            
            if not credential_info:
                click.echo(f"No credentials found for connector: {connector_name}", err=True)
                return 1
            
            if format == "json":
                click.echo(json.dumps(credential_info, indent=2))
            elif format == "yaml":
                click.echo(yaml.dump(credential_info, default_flow_style=False))
            else:  # table format
                click.echo(f"Connector: {credential_info['connector_name']}")
                click.echo(f"Auth Type: {credential_info['auth_type']}")
                click.echo(f"Description: {credential_info['description'] or 'None'}")
                click.echo(f"Expires: {credential_info['expires_at'] or 'Never'}")
                
                if credential_info['tags']:
                    click.echo("Tags:")
                    for key, value in credential_info['tags'].items():
                        click.echo(f"  {key}: {value}")
                
                if credential_info['config']:
                    click.echo("Configuration:")
                    for key, value in credential_info['config'].items():
                        if value:  # Only show non-empty values
                            click.echo(f"  {key}: {value}")
            
            await close_secret_storage()
            return 0
            
        except SecretNotFoundError:
            click.echo(f"No credentials found for connector: {connector_name}", err=True)
            return 1
        except SecretStorageError as e:
            click.echo(f"Error retrieving credentials: {e}", err=True)
            return 1
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            return 1
    
    sys.exit(asyncio.run(_show_credentials()))


@credentials.command()
@click.argument('connector_name')
@click.option('--force', 
              is_flag=True,
              help='Delete without confirmation prompt')
def delete(connector_name: str, force: bool):
    """Delete credentials for a connector."""
    
    async def _delete_credentials():
        try:
            storage = await get_secret_storage()
            
            # Check if credentials exist
            api_key_name = generate_secret_name(connector_name, SecretType.API_KEY)
            oauth_client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
            oauth_client_secret_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_SECRET)
            
            exists = (await storage.secret_exists(api_key_name) or 
                     await storage.secret_exists(oauth_client_id_name))
            
            if not exists:
                click.echo(f"No credentials found for connector: {connector_name}", err=True)
                return 1
            
            if not force:
                if not click.confirm(f"Delete all credentials for connector '{connector_name}'?"):
                    click.echo("Cancelled.")
                    return 0
            
            # Delete all possible credentials
            secrets_deleted = 0
            
            for secret_name in [api_key_name, oauth_client_id_name, oauth_client_secret_name]:
                if await storage.secret_exists(secret_name):
                    await storage.delete_secret(secret_name)
                    secrets_deleted += 1
            
            if secrets_deleted > 0:
                click.echo(f"✓ Deleted {secrets_deleted} credential(s) for connector '{connector_name}'")
            else:
                click.echo(f"No credentials found for connector: {connector_name}", err=True)
                return 1
            
            await close_secret_storage()
            return 0
            
        except SecretStorageError as e:
            click.echo(f"Error deleting credentials: {e}", err=True)
            return 1
        except Exception as e:
            click.echo(f"Unexpected error: {e}", err=True)
            return 1
    
    sys.exit(asyncio.run(_delete_credentials()))


if __name__ == "__main__":
    credentials()