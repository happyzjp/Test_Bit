from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PermissionBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    menu_path: Optional[str] = None
    menu_icon: Optional[str] = None
    menu_order: int = 0
    parent_id: Optional[int] = None


class PermissionCreate(PermissionBase):
    pass


class PermissionResponse(PermissionBase):
    id: int
    is_active: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        
    @classmethod
    def from_orm(cls, obj):
        """Create from ORM object."""
        return cls(
            id=obj.id,
            code=obj.code,
            name=obj.name,
            description=obj.description,
            menu_path=obj.menu_path,
            menu_icon=obj.menu_icon,
            menu_order=obj.menu_order,
            parent_id=obj.parent_id,
            is_active=obj.is_active,
            created_at=obj.created_at
        )


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permission_ids: List[int] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None


class RoleResponse(RoleBase):
    id: int
    is_system: bool
    is_active: bool
    permissions: List[PermissionResponse] = []
    user_count: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RoleListResponse(BaseModel):
    roles: List[RoleResponse]
    total: int

