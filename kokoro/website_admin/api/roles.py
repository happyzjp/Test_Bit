from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from kokoro.common.database import get_db
from kokoro.website_admin.models.user import User
from kokoro.website_admin.models.role import Role, Permission, RolePermission
from kokoro.website_admin.schemas.role import (
    RoleCreate, RoleUpdate, RoleResponse, PermissionResponse, RoleListResponse
)
from kokoro.website_admin.api.auth import get_current_user, DEFAULT_ADMIN_EMAIL
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


def check_admin_permission(current_user: User) -> bool:
    """Check if user has admin role."""
    return current_user.role_obj and current_user.role_obj.name == "admin"


@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all permissions (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list permissions"
        )
    
    permissions = db.query(Permission).filter(Permission.is_active == True).order_by(Permission.menu_order).all()
    return permissions


@router.get("/roles", response_model=RoleListResponse)
async def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all roles (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list roles"
        )
    
    roles = db.query(Role).all()
    role_responses = []
    for role in roles:
        # Count users with this role
        user_count = db.query(func.count(User.id)).filter(User.role_id == role.id).scalar()
        
        role_response = RoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            is_active=role.is_active,
            permissions=[
                PermissionResponse(
                    id=p.permission.id,
                    code=p.permission.code,
                    name=p.permission.name,
                    description=p.permission.description,
                    menu_path=p.permission.menu_path,
                    menu_icon=p.permission.menu_icon,
                    menu_order=p.permission.menu_order,
                    parent_id=p.permission.parent_id,
                    is_active=p.permission.is_active,
                    created_at=p.permission.created_at
                )
                for p in role.permissions if p.permission.is_active
            ],
            user_count=user_count,
            created_at=role.created_at
        )
        role_responses.append(role_response)
    
    return RoleListResponse(roles=role_responses, total=len(role_responses))


@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific role (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view roles"
        )
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user_count = db.query(func.count(User.id)).filter(User.role_id == role.id).scalar()
    
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        is_active=role.is_active,
        permissions=[PermissionResponse.from_orm(p.permission) for p in role.permissions if p.permission.is_active],
        user_count=user_count,
        created_at=role.created_at
    )


@router.post("/roles", response_model=RoleResponse)
async def create_role(
    role_data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new role (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create roles"
        )
    
    # Check if role name already exists
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists"
        )
    
    # Create role
    new_role = Role(
        name=role_data.name,
        description=role_data.description,
        is_system=False
    )
    db.add(new_role)
    db.flush()  # Get the ID
    
    # Add permissions
    if role_data.permission_ids:
        permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
        for permission in permissions:
            role_permission = RolePermission(role_id=new_role.id, permission_id=permission.id)
            db.add(role_permission)
    
    db.commit()
    db.refresh(new_role)
    
    logger.info(f"Role created: {new_role.name} by {current_user.email}")
    
    user_count = db.query(func.count(User.id)).filter(User.role_id == new_role.id).scalar()
    return RoleResponse(
        id=new_role.id,
        name=new_role.name,
        description=new_role.description,
        is_system=new_role.is_system,
        is_active=new_role.is_active,
        permissions=[PermissionResponse.from_orm(p.permission) for p in new_role.permissions if p.permission.is_active],
        user_count=user_count,
        created_at=new_role.created_at
    )


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a role (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update roles"
        )
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Prevent modifying system roles
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify system roles"
        )
    
    # Update role fields
    if role_data.name is not None:
        # Check if name already exists (excluding current role)
        existing_role = db.query(Role).filter(Role.name == role_data.name, Role.id != role_id).first()
        if existing_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role with this name already exists"
            )
        role.name = role_data.name
    
    if role_data.description is not None:
        role.description = role_data.description
    
    if role_data.is_active is not None:
        role.is_active = role_data.is_active
    
    # Update permissions
    if role_data.permission_ids is not None:
        # Remove existing permissions
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        # Add new permissions
        if role_data.permission_ids:
            permissions = db.query(Permission).filter(Permission.id.in_(role_data.permission_ids)).all()
            for permission in permissions:
                role_permission = RolePermission(role_id=role_id, permission_id=permission.id)
                db.add(role_permission)
    
    db.commit()
    db.refresh(role)
    
    logger.info(f"Role updated: {role.name} by {current_user.email}")
    
    user_count = db.query(func.count(User.id)).filter(User.role_id == role.id).scalar()
    return RoleResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        is_active=role.is_active,
        permissions=[PermissionResponse.from_orm(p.permission) for p in role.permissions if p.permission.is_active],
        user_count=user_count,
        created_at=role.created_at
    )


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a role (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete roles"
        )
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Prevent deleting system roles
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system roles"
        )
    
    # Check if role has users
    user_count = db.query(func.count(User.id)).filter(User.role_id == role_id).scalar()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role with {user_count} user(s). Please reassign users first."
        )
    
    db.delete(role)
    db.commit()
    
    logger.info(f"Role deleted: {role.name} by {current_user.email}")
    return {"message": "Role deleted successfully"}


@router.get("/roles/{role_id}/users", response_model=List[dict])
async def get_role_users(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get users with a specific role (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view role users"
        )
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    users = db.query(User).filter(User.role_id == role_id).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]

