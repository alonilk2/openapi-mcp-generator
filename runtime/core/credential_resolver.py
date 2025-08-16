"""
Credential resolution service for runtime tool execution.

This module provides services for securely resolving and injecting credentials
when executing connector tools, ensuring that authentication secrets are properly
applied based on the tool's auth configuration.
"""

import asyncio
from typing import Dict, Optional, Any, List
import logging
from dataclasses import dataclass

from .secret_factory import get_secret_storage
from .secrets import SecretType, SecretNotFoundError, SecretStorageError, generate_secret_name
from models.manifest import ConnectorTool, ApiKeyAuth, OAuth2ClientCredentialsAuth, NoAuth

logger = logging.getLogger(__name__)


@dataclass
class ResolvedCredentials:
    """Container for resolved credential data."""
    
    auth_type: str
    headers: Dict[str, str]
    query_params: Dict[str, str]
    cookies: Dict[str, str]
    oauth_token: Optional[str] = None
    
    def has_credentials(self) -> bool:
        """Check if any credentials were resolved."""
        return bool(self.headers or self.query_params or self.cookies or self.oauth_token)

    def redacted_summary(self) -> Dict[str, Any]:
        """Get a summary with sensitive values redacted for logging."""
        return {
            "auth_type": self.auth_type,
            "has_headers": bool(self.headers),
            "has_query_params": bool(self.query_params),
            "has_cookies": bool(self.cookies),
            "has_oauth_token": bool(self.oauth_token),
            "header_names": list(self.headers.keys()) if self.headers else [],
            "query_param_names": list(self.query_params.keys()) if self.query_params else [],
            "cookie_names": list(self.cookies.keys()) if self.cookies else []
        }


class CredentialResolutionError(Exception):
    """Raised when credential resolution fails."""
    pass


class CredentialResolver:
    """
    Service for resolving credentials for connector tools.
    
    This service handles the secure resolution of stored credentials and their
    injection into HTTP requests based on the tool's authentication configuration.
    """

    def __init__(self):
        """Initialize the credential resolver."""
        self._oauth_token_cache: Dict[str, str] = {}  # Simple in-memory cache for OAuth tokens

    async def resolve_credentials(self, tool: ConnectorTool, connector_name: str) -> ResolvedCredentials:
        """
        Resolve credentials for a connector tool.
        
        Args:
            tool: The connector tool that needs authentication
            connector_name: Name of the connector
            
        Returns:
            ResolvedCredentials with authentication data
            
        Raises:
            CredentialResolutionError: If credential resolution fails
        """
        try:
            if tool.auth.type == "none":
                return ResolvedCredentials(
                    auth_type="none",
                    headers={},
                    query_params={},
                    cookies={}
                )
            elif tool.auth.type == "api_key":
                return await self._resolve_api_key_credentials(tool, connector_name)
            elif tool.auth.type == "oauth2_client_credentials":
                return await self._resolve_oauth2_credentials(tool, connector_name)
            else:
                raise CredentialResolutionError(f"Unsupported auth type: {tool.auth.type}")
                
        except Exception as e:
            logger.error(f"Failed to resolve credentials for tool '{tool.name}': {e}")
            raise CredentialResolutionError(f"Credential resolution failed: {str(e)}")

    async def _resolve_api_key_credentials(self, tool: ConnectorTool, connector_name: str) -> ResolvedCredentials:
        """Resolve API key credentials."""
        if not isinstance(tool.auth, ApiKeyAuth):
            raise CredentialResolutionError("Tool auth is not API key type")

        try:
            storage = await get_secret_storage()
            secret_name = generate_secret_name(connector_name, SecretType.API_KEY)
            
            secret_value = await storage.get_secret(secret_name)
            api_key = secret_value.value
            
            # Get auth configuration from secret metadata tags
            tags = secret_value.metadata.tags
            key_name = tags.get("key_name") or tool.auth.key_name
            location = tags.get("location") or tool.auth.location
            scheme = tags.get("scheme") or tool.auth.scheme
            
            # Build the auth value
            if scheme:
                auth_value = f"{scheme} {api_key}"
            else:
                auth_value = api_key
            
            # Place the auth value in the appropriate location
            headers = {}
            query_params = {}
            cookies = {}
            
            if location == "header":
                headers[key_name] = auth_value
            elif location == "query":
                query_params[key_name] = auth_value
            elif location == "cookie":
                cookies[key_name] = auth_value
            else:
                raise CredentialResolutionError(f"Unsupported API key location: {location}")
            
            logger.info(f"Resolved API key credentials for connector '{connector_name}' tool '{tool.name}'")
            
            return ResolvedCredentials(
                auth_type="api_key",
                headers=headers,
                query_params=query_params,
                cookies=cookies
            )
            
        except SecretNotFoundError:
            raise CredentialResolutionError(f"No API key found for connector '{connector_name}'")
        except SecretStorageError as e:
            raise CredentialResolutionError(f"Failed to retrieve API key: {str(e)}")

    async def _resolve_oauth2_credentials(self, tool: ConnectorTool, connector_name: str) -> ResolvedCredentials:
        """Resolve OAuth2 client credentials."""
        if not isinstance(tool.auth, OAuth2ClientCredentialsAuth):
            raise CredentialResolutionError("Tool auth is not OAuth2 client credentials type")

        try:
            # Check if we have a cached access token
            cache_key = f"{connector_name}:oauth2"
            if cache_key in self._oauth_token_cache:
                access_token = self._oauth_token_cache[cache_key]
                logger.info(f"Using cached OAuth2 token for connector '{connector_name}'")
                
                return ResolvedCredentials(
                    auth_type="oauth2_client_credentials",
                    headers={"Authorization": f"Bearer {access_token}"},
                    query_params={},
                    cookies={},
                    oauth_token=access_token
                )
            
            # Get OAuth2 credentials from storage
            storage = await get_secret_storage()
            client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
            client_secret_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_SECRET)
            
            try:
                client_id_secret = await storage.get_secret(client_id_name)
                client_secret_secret = await storage.get_secret(client_secret_name)
                
                client_id = client_id_secret.value
                client_secret = client_secret_secret.value
                
                # Get OAuth2 configuration from metadata
                tags = client_id_secret.metadata.tags
                token_url = tags.get("token_url") or tool.auth.token_url
                scopes_str = tags.get("scopes", "")
                scopes = scopes_str.split(",") if scopes_str else (tool.auth.scopes or [])
                
                if not token_url:
                    raise CredentialResolutionError("OAuth2 token URL not configured")
                
                # Request access token
                access_token = await self._request_oauth2_token(
                    token_url=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=scopes
                )
                
                # Cache the token (simple in-memory cache without expiration for MVP)
                self._oauth_token_cache[cache_key] = access_token
                
                logger.info(f"Resolved OAuth2 credentials for connector '{connector_name}' tool '{tool.name}'")
                
                return ResolvedCredentials(
                    auth_type="oauth2_client_credentials",
                    headers={"Authorization": f"Bearer {access_token}"},
                    query_params={},
                    cookies={},
                    oauth_token=access_token
                )
                
            except SecretNotFoundError:
                raise CredentialResolutionError(f"OAuth2 credentials not found for connector '{connector_name}'")
                
        except SecretStorageError as e:
            raise CredentialResolutionError(f"Failed to retrieve OAuth2 credentials: {str(e)}")

    async def _request_oauth2_token(self, token_url: str, client_id: str, client_secret: str, scopes: List[str]) -> str:
        """Request an OAuth2 access token using client credentials flow."""
        import httpx
        
        try:
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret
            }
            
            if scopes:
                data["scope"] = " ".join(scopes)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code != 200:
                    raise CredentialResolutionError(
                        f"OAuth2 token request failed: {response.status_code} {response.text}"
                    )
                
                token_data = response.json()
                access_token = token_data.get("access_token")
                
                if not access_token:
                    raise CredentialResolutionError("No access token in OAuth2 response")
                
                logger.info(f"Successfully obtained OAuth2 access token from {token_url}")
                return access_token
                
        except httpx.RequestError as e:
            raise CredentialResolutionError(f"Failed to request OAuth2 token: {str(e)}")
        except Exception as e:
            raise CredentialResolutionError(f"OAuth2 token request error: {str(e)}")

    def clear_oauth_cache(self, connector_name: Optional[str] = None) -> None:
        """
        Clear OAuth token cache.
        
        Args:
            connector_name: If provided, clear cache only for this connector.
                          If None, clear all cached tokens.
        """
        if connector_name:
            cache_key = f"{connector_name}:oauth2"
            self._oauth_token_cache.pop(cache_key, None)
            logger.info(f"Cleared OAuth token cache for connector '{connector_name}'")
        else:
            self._oauth_token_cache.clear()
            logger.info("Cleared all OAuth token cache")

    async def validate_credentials(self, tool: ConnectorTool, connector_name: str) -> bool:
        """
        Validate that credentials exist and are accessible for a tool.
        
        Args:
            tool: The connector tool to validate credentials for
            connector_name: Name of the connector
            
        Returns:
            True if credentials are valid and accessible
        """
        try:
            credentials = await self.resolve_credentials(tool, connector_name)
            return credentials.has_credentials() or tool.auth.type == "none"
        except CredentialResolutionError:
            return False


# Global credential resolver instance
_credential_resolver: Optional[CredentialResolver] = None


def get_credential_resolver() -> CredentialResolver:
    """
    Get the global credential resolver instance.
    
    Returns:
        CredentialResolver instance
    """
    global _credential_resolver
    
    if _credential_resolver is None:
        _credential_resolver = CredentialResolver()
    
    return _credential_resolver


def reset_credential_resolver() -> None:
    """Reset the global credential resolver instance (useful for testing)."""
    global _credential_resolver
    _credential_resolver = None