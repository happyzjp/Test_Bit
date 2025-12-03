from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(..., description="API key name")
    description: Optional[str] = Field(None, description="API key description")
    expires_at: Optional[datetime] = Field(None, description="Expiration date")


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, description="API key name")
    description: Optional[str] = Field(None, description="API key description")
    is_active: Optional[bool] = Field(None, description="Whether the key is active")
    expires_at: Optional[datetime] = Field(None, description="Expiration date")


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key: str
    description: Optional[str]
    is_active: bool
    created_by: Optional[str]
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyResponse]
    total: int

