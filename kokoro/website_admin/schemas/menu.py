from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MenuBase(BaseModel):
    name: str = Field(..., description="Menu display name")
    code: str = Field(..., description="Menu code (unique identifier)")
    path: str = Field(..., description="Menu route path")
    icon: Optional[str] = Field(None, description="Icon name from lucide-react")
    parent_id: Optional[int] = Field(None, description="Parent menu ID")
    category: Optional[str] = Field(None, description="Menu category")
    order: int = Field(0, description="Display order")
    is_active: bool = Field(True, description="Whether the menu is active")
    permission_code: Optional[str] = Field(None, description="Required permission code")
    description: Optional[str] = Field(None, description="Menu description")


class MenuCreate(MenuBase):
    pass


class MenuUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    category: Optional[str] = None
    order: Optional[int] = None
    is_active: Optional[bool] = None
    permission_code: Optional[str] = None
    description: Optional[str] = None


class MenuResponse(MenuBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    has_children: Optional[bool] = None  # Indicates if menu has children (for lazy loading)
    
    class Config:
        from_attributes = True


class MenuListResponse(BaseModel):
    menus: List[MenuResponse]
    total: int

