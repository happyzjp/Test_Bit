from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from kokoro.common.database import get_db
from kokoro.website_admin.models.api_key import ApiKey
from kokoro.website_admin.schemas.api_key import (
    ApiKeyCreate, ApiKeyUpdate, ApiKeyResponse, ApiKeyListResponse
)
from kokoro.common.utils.logging import setup_logger
import secrets
import hashlib
from datetime import datetime, timezone

router = APIRouter()
logger = setup_logger(__name__)


def generate_api_key() -> str:
    """Generate a secure API key."""
    # Generate a random token
    token = secrets.token_urlsafe(32)
    # Create a prefixed key for easy identification
    return f"kokoro_{token}"


def hash_api_key(key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


@router.post("", response_model=ApiKeyResponse)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    db: Session = Depends(get_db)
):
    """Create a new API key."""
    try:
        # Generate a new API key
        new_key = generate_api_key()
        key_hash = hash_api_key(new_key)
        
        # Check if key already exists (very unlikely but check anyway)
        existing = db.query(ApiKey).filter(ApiKey.key == key_hash).first()
        if existing:
            # Regenerate if collision
            new_key = generate_api_key()
            key_hash = hash_api_key(new_key)
        
        # Create API key record - store both plain key (for display) and hash (for verification)
        # Note: In production, you might want to store only hash and return plain key only once
        api_key = ApiKey(
            name=api_key_data.name,
            key=key_hash,  # Store hashed version for security
            description=api_key_data.description,
            is_active=True,
            expires_at=api_key_data.expires_at,
            created_by="system"  # TODO: Get from auth context
        )
        
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        # Return the plain key only once (for user to copy and save)
        # After this, the plain key won't be available again
        response = ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=new_key,  # Return plain key for user to copy (only shown once)
            description=api_key.description,
            is_active=api_key.is_active,
            created_by=api_key.created_by,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at
        )
        
        logger.info(f"API key created: {api_key.name} (ID: {api_key.id})")
        return response
        
    except Exception as e:
        logger.error(f"Error creating API key: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {str(e)}")


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all API keys."""
    try:
        total = db.query(ApiKey).count()
        api_keys = db.query(ApiKey).offset(skip).limit(limit).all()
        
        # Return keys without showing the actual key value (for security)
        # Since we store hashes, we can't show partial key - show masked version
        response_keys = []
        for key in api_keys:
            response_keys.append(ApiKeyResponse(
                id=key.id,
                name=key.name,
                key="kokoro_***" + (key.key[-12:] if len(key.key) > 12 else "***"),  # Show partial hash for identification
                description=key.description,
                is_active=key.is_active,
                created_by=key.created_by,
                last_used_at=key.last_used_at,
                expires_at=key.expires_at,
                created_at=key.created_at,
                updated_at=key.updated_at
            ))
        
        return ApiKeyListResponse(api_keys=response_keys, total=total)
        
    except Exception as e:
        logger.error(f"Error listing API keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")


@router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific API key by ID."""
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key="kokoro_***" + (api_key.key[-12:] if api_key.key and len(api_key.key) > 12 else "***"),
            description=api_key.description,
            is_active=api_key.is_active,
            created_by=api_key.created_by,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting API key: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get API key: {str(e)}")


@router.put("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: int,
    api_key_data: ApiKeyUpdate,
    db: Session = Depends(get_db)
):
    """Update an API key."""
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        if api_key_data.name is not None:
            api_key.name = api_key_data.name
        if api_key_data.description is not None:
            api_key.description = api_key_data.description
        if api_key_data.is_active is not None:
            api_key.is_active = api_key_data.is_active
        if api_key_data.expires_at is not None:
            api_key.expires_at = api_key_data.expires_at
        
        db.commit()
        db.refresh(api_key)
        
        logger.info(f"API key updated: {api_key.name} (ID: {api_key.id})")
        
        return ApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key="kokoro_***" + (api_key.key[-12:] if api_key.key and len(api_key.key) > 12 else "***"),
            description=api_key.description,
            is_active=api_key.is_active,
            created_by=api_key.created_by,
            last_used_at=api_key.last_used_at,
            expires_at=api_key.expires_at,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating API key: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update API key: {str(e)}")


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db)
):
    """Delete an API key."""
    try:
        api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        db.delete(api_key)
        db.commit()
        
        logger.info(f"API key deleted: {api_key.name} (ID: {api_key.id})")
        
        return {"message": "API key deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting API key: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete API key: {str(e)}")

