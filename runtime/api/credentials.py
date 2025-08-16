"""
Credential management API endpoints.

This module provides REST API endpoints for managing connector credentials,
including storing, retrieving, updating, and deleting authentication secrets.
"""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from core.secret_factory import get_secret_storage
from core.secrets import SecretType, SecretNotFoundError, SecretStorageError, generate_secret_name
from models.manifest import ApiKeyAuth, OAuth2ClientCredentialsAuth


router = APIRouter(prefix="/v1/credentials", tags=["credentials"])


class CredentialRequest(BaseModel):
    """Request model for storing credentials."""
    
    connector_name: str = Field(
        ..., 
        description="Name of the connector (e.g., '@github/api')",
        min_length=1,
        max_length=100
    )
    
    auth_type: str = Field(
        ...,
        description="Type of authentication (api_key, oauth2_client_credentials)"
    )
    
    credentials: Dict[str, Any] = Field(
        ...,
        description="Credential data specific to the auth type"
    )
    
    description: Optional[str] = Field(
        None,
        description="Optional description for the credentials",
        max_length=500
    )
    
    tags: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Optional key-value tags for the credentials"
    )
    
    expires_at: Optional[str] = Field(
        None,
        description="Optional expiration date (ISO 8601 format)"
    )

    @field_validator('auth_type')
    @classmethod
    def validate_auth_type(cls, v):
        """Validate that auth_type is supported."""
        supported_types = {"api_key", "oauth2_client_credentials"}
        if v not in supported_types:
            raise ValueError(f"Unsupported auth_type. Must be one of: {supported_types}")
        return v

    @field_validator('credentials')
    @classmethod
    def validate_credentials(cls, v, info):
        """Validate credentials based on auth_type."""
        # Get auth_type from validation info
        data = info.data if hasattr(info, 'data') else {}
        auth_type = data.get('auth_type')
        
        if auth_type == "api_key":
            required_fields = {"value"}
            optional_fields = {"key_name", "location", "scheme"}
        elif auth_type == "oauth2_client_credentials":
            required_fields = {"client_id", "client_secret"}
            optional_fields = {"token_url", "scopes"}
        else:
            # Should not reach here due to auth_type validation
            raise ValueError("Invalid auth_type")
        
        # Check required fields
        missing_fields = required_fields - set(v.keys())
        if missing_fields:
            raise ValueError(f"Missing required fields for {auth_type}: {missing_fields}")
        
        # Check for unexpected fields
        all_allowed = required_fields | optional_fields
        unexpected_fields = set(v.keys()) - all_allowed
        if unexpected_fields:
            raise ValueError(f"Unexpected fields for {auth_type}: {unexpected_fields}")
        
        return v


class CredentialUpdateRequest(BaseModel):
    """Request model for updating credentials."""
    
    credentials: Optional[Dict[str, Any]] = Field(
        None,
        description="Updated credential data"
    )
    
    description: Optional[str] = Field(
        None,
        description="Updated description",
        max_length=500
    )
    
    tags: Optional[Dict[str, str]] = Field(
        None,
        description="Updated tags"
    )
    
    expires_at: Optional[str] = Field(
        None,
        description="Updated expiration date (ISO 8601 format)"
    )


class CredentialResponse(BaseModel):
    """Response model for credential metadata (without values)."""
    
    name: str = Field(..., description="Credential name")
    connector_name: str = Field(..., description="Connector name")
    auth_type: str = Field(..., description="Authentication type")
    description: Optional[str] = Field(None, description="Description")
    tags: Dict[str, str] = Field(default_factory=dict, description="Tags")
    expires_at: Optional[str] = Field(None, description="Expiration date")
    has_credentials: bool = Field(..., description="Whether credentials are stored")


class CredentialListResponse(BaseModel):
    """Response model for listing credentials."""
    
    credentials: List[CredentialResponse] = Field(..., description="List of credentials")
    total: int = Field(..., description="Total number of credentials")


@router.post("/", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def store_credentials(request: CredentialRequest):
    """
    Store credentials for a connector.
    
    This endpoint stores authentication credentials that will be used when
    calling tools from the specified connector.
    """
    try:
        storage = await get_secret_storage()
        
        # Store secrets based on auth type
        if request.auth_type == "api_key":
            # Store the API key value
            secret_name = generate_secret_name(request.connector_name, SecretType.API_KEY)
            await storage.store_secret(
                name=secret_name,
                value=request.credentials["value"],
                secret_type=SecretType.API_KEY,
                connector_name=request.connector_name,
                description=request.description,
                tags={
                    **request.tags,
                    "key_name": request.credentials.get("key_name", ""),
                    "location": request.credentials.get("location", "header"),
                    "scheme": request.credentials.get("scheme", "")
                },
                expires_at=request.expires_at
            )
            
        elif request.auth_type == "oauth2_client_credentials":
            # Store client ID and client secret separately
            client_id_name = generate_secret_name(request.connector_name, SecretType.OAUTH2_CLIENT_ID)
            client_secret_name = generate_secret_name(request.connector_name, SecretType.OAUTH2_CLIENT_SECRET)
            
            base_tags = {
                **request.tags,
                "token_url": request.credentials.get("token_url", ""),
                "scopes": ",".join(request.credentials.get("scopes", []))
            }
            
            await storage.store_secret(
                name=client_id_name,
                value=request.credentials["client_id"],
                secret_type=SecretType.OAUTH2_CLIENT_ID,
                connector_name=request.connector_name,
                description=f"OAuth2 Client ID - {request.description or ''}".strip(),
                tags=base_tags,
                expires_at=request.expires_at
            )
            
            await storage.store_secret(
                name=client_secret_name,
                value=request.credentials["client_secret"],
                secret_type=SecretType.OAUTH2_CLIENT_SECRET,
                connector_name=request.connector_name,
                description=f"OAuth2 Client Secret - {request.description or ''}".strip(),
                tags=base_tags,
                expires_at=request.expires_at
            )
        
        return CredentialResponse(
            name=generate_secret_name(request.connector_name, SecretType.API_KEY if request.auth_type == "api_key" else SecretType.OAUTH2_CLIENT_ID),
            connector_name=request.connector_name,
            auth_type=request.auth_type,
            description=request.description,
            tags=request.tags,
            expires_at=request.expires_at,
            has_credentials=True
        )
        
    except SecretStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/", response_model=CredentialListResponse)
async def list_credentials(
    connector_name: Optional[str] = None,
    auth_type: Optional[str] = None
):
    """
    List stored credentials with optional filtering.
    
    Returns metadata about stored credentials without exposing the actual
    credential values.
    """
    try:
        storage = await get_secret_storage()
        
        # Convert auth_type to SecretType for filtering
        secret_type_filter = None
        if auth_type:
            if auth_type == "api_key":
                secret_type_filter = SecretType.API_KEY
            elif auth_type == "oauth2_client_credentials":
                secret_type_filter = SecretType.OAUTH2_CLIENT_ID
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid auth_type: {auth_type}"
                )
        
        secrets = await storage.list_secrets(
            connector_name=connector_name,
            secret_type=secret_type_filter
        )
        
        # Group OAuth2 credentials by connector
        credentials_map = {}
        
        for secret in secrets:
            if secret.secret_type == SecretType.API_KEY:
                credentials_map[secret.connector_name] = CredentialResponse(
                    name=secret.name,
                    connector_name=secret.connector_name,
                    auth_type="api_key",
                    description=secret.description,
                    tags={k: v for k, v in secret.tags.items() if k not in ["key_name", "location", "scheme"]},
                    expires_at=secret.expires_at,
                    has_credentials=True
                )
            elif secret.secret_type == SecretType.OAUTH2_CLIENT_ID:
                credentials_map[secret.connector_name] = CredentialResponse(
                    name=secret.name,
                    connector_name=secret.connector_name,
                    auth_type="oauth2_client_credentials",
                    description=secret.description,
                    tags={k: v for k, v in secret.tags.items() if k not in ["token_url", "scopes"]},
                    expires_at=secret.expires_at,
                    has_credentials=True
                )
        
        credentials_list = list(credentials_map.values())
        
        return CredentialListResponse(
            credentials=credentials_list,
            total=len(credentials_list)
        )
        
    except SecretStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/{connector_name}", response_model=CredentialResponse)
async def get_credentials(connector_name: str):
    """
    Get credential metadata for a specific connector.
    
    Returns metadata about the stored credentials without exposing the actual
    credential values.
    """
    try:
        storage = await get_secret_storage()
        
        # Try to find API key first
        api_key_name = generate_secret_name(connector_name, SecretType.API_KEY)
        oauth_client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
        
        if await storage.secret_exists(api_key_name):
            secret_value = await storage.get_secret(api_key_name)
            return CredentialResponse(
                name=secret_value.metadata.name,
                connector_name=secret_value.metadata.connector_name,
                auth_type="api_key",
                description=secret_value.metadata.description,
                tags={k: v for k, v in secret_value.metadata.tags.items() if k not in ["key_name", "location", "scheme"]},
                expires_at=secret_value.metadata.expires_at,
                has_credentials=True
            )
        elif await storage.secret_exists(oauth_client_id_name):
            secret_value = await storage.get_secret(oauth_client_id_name)
            return CredentialResponse(
                name=secret_value.metadata.name,
                connector_name=secret_value.metadata.connector_name,
                auth_type="oauth2_client_credentials",
                description=secret_value.metadata.description,
                tags={k: v for k, v in secret_value.metadata.tags.items() if k not in ["token_url", "scopes"]},
                expires_at=secret_value.metadata.expires_at,
                has_credentials=True
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No credentials found for connector: {connector_name}"
            )
            
    except SecretNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for connector: {connector_name}"
        )
    except SecretStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.delete("/{connector_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credentials(connector_name: str):
    """
    Delete all credentials for a specific connector.
    
    This will remove all stored authentication secrets for the connector.
    """
    try:
        storage = await get_secret_storage()
        
        # Try to delete both API key and OAuth2 credentials
        secrets_deleted = 0
        
        # Delete API key if exists
        api_key_name = generate_secret_name(connector_name, SecretType.API_KEY)
        if await storage.secret_exists(api_key_name):
            await storage.delete_secret(api_key_name)
            secrets_deleted += 1
        
        # Delete OAuth2 credentials if they exist
        client_id_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_ID)
        client_secret_name = generate_secret_name(connector_name, SecretType.OAUTH2_CLIENT_SECRET)
        
        if await storage.secret_exists(client_id_name):
            await storage.delete_secret(client_id_name)
            secrets_deleted += 1
            
        if await storage.secret_exists(client_secret_name):
            await storage.delete_secret(client_secret_name)
            secrets_deleted += 1
        
        if secrets_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No credentials found for connector: {connector_name}"
            )
        
    except SecretNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No credentials found for connector: {connector_name}"
        )
    except SecretStorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete credentials: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )