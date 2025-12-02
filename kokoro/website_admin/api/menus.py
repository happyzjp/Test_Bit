from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List
from kokoro.common.database import SessionLocal
from kokoro.website_admin.models.menu import Menu
from kokoro.website_admin.schemas.menu import MenuCreate, MenuUpdate, MenuResponse, MenuListResponse
from kokoro.website_admin.api.auth import get_current_user
from kokoro.website_admin.models.user import User
from kokoro.website_admin.models.role import Role, RolePermission, Permission
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/menus", response_model=MenuListResponse)
def list_menus(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all menus"""
    menus = db.query(Menu).order_by(Menu.order, Menu.id).offset(skip).limit(limit).all()
    total = db.query(Menu).count()
    return MenuListResponse(menus=[MenuResponse.model_validate(m) for m in menus], total=total)


@router.get("/menus/user", response_model=List[MenuResponse])
def get_user_menus(
    parent_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get menus visible to the current user based on their permissions.
    If parent_id is None, returns root menus (first level only).
    If parent_id is provided, returns children of that menu.
    """
    # Build base query
    query = db.query(Menu).filter(Menu.is_active == True)
    
    # Filter by parent_id (None for root menus)
    if parent_id is None:
        query = query.filter(Menu.parent_id.is_(None))
    else:
        query = query.filter(Menu.parent_id == parent_id)
    
    # Admin users see all active menus
    if current_user.role_obj and current_user.role_obj.name == "admin":
        menus = query.order_by(Menu.order, Menu.id).all()
    else:
        # Get user's permissions
        user_permissions = set()
        if current_user.role_obj:
            logger.debug(f"User {current_user.email} has role: {current_user.role_obj.name}")
            for role_perm in current_user.role_obj.permissions:
                # role_perm is a RolePermission object, access permission via role_perm.permission
                if role_perm.permission and role_perm.permission.is_active:
                    user_permissions.add(role_perm.permission.code)
                    logger.debug(f"User {current_user.email} has permission: {role_perm.permission.code}")
        
        logger.debug(f"User {current_user.email} permissions: {user_permissions}")
        
        # Get menus that user has permission for or menus without permission requirement
        menus = query.order_by(Menu.order, Menu.id).all()
        
        # Helper function to check if user has permission for any child menu
        def has_visible_children(menu_id: int) -> bool:
            child_menus = db.query(Menu).filter(
                Menu.parent_id == menu_id,
                Menu.is_active == True
            ).all()
            
            if not child_menus:
                return False
            
            for child in child_menus:
                # Child is visible if it has no permission requirement or user has permission
                if not child.permission_code or child.permission_code in user_permissions:
                    return True
            return False
        
        # Filter menus based on permissions
        visible_menus = []
        for menu in menus:
            menu_visible = False
            
            if not menu.permission_code:
                # Menu without permission requirement
                # If it has children, check if user has permission for any child
                # If no children, menu is visible
                if has_visible_children(menu.id):
                    menu_visible = True
                    logger.debug(f"Menu {menu.name} ({menu.code}) has no permission requirement but has visible children, visible")
                else:
                    # Check if menu has any children at all
                    child_count = db.query(Menu).filter(
                        Menu.parent_id == menu.id,
                        Menu.is_active == True
                    ).count()
                    if child_count == 0:
                        # No children, menu is visible
                        menu_visible = True
                        logger.debug(f"Menu {menu.name} ({menu.code}) has no permission requirement and no children, visible")
                    else:
                        logger.debug(f"Menu {menu.name} ({menu.code}) has no permission requirement but no visible children, hidden")
            elif menu.permission_code in user_permissions:
                # User has permission for this menu
                menu_visible = True
                logger.debug(f"Menu {menu.name} ({menu.code}) requires {menu.permission_code}, user has permission, visible")
            else:
                # User doesn't have permission for this menu
                # But if it's a parent menu, check if user has permission for any child
                if has_visible_children(menu.id):
                    menu_visible = True
                    logger.debug(f"Menu {menu.name} ({menu.code}) requires {menu.permission_code} (no permission), but has visible children, visible")
                else:
                    logger.debug(f"Menu {menu.name} ({menu.code}) requires {menu.permission_code}, user does not have permission and no visible children, hidden")
            
            if menu_visible:
                visible_menus.append(menu)
        menus = visible_menus
    
    # Check if each menu has children and add to response
    menu_responses = []
    for menu in menus:
        # Check if menu has children (for lazy loading)
        has_children = db.query(Menu).filter(
            Menu.parent_id == menu.id,
            Menu.is_active == True
        ).first() is not None
        # Create MenuResponse with has_children field
        menu_response = MenuResponse.model_validate(menu)
        menu_response.has_children = has_children
        menu_responses.append(menu_response)
    
    return menu_responses


@router.get("/menus/{menu_id}/children", response_model=List[MenuResponse])
def get_menu_children(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get children menus of a specific menu"""
    # Check if menu exists
    parent_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not parent_menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    
    # Build query for children
    query = db.query(Menu).filter(
        Menu.parent_id == menu_id,
        Menu.is_active == True
    )
    
    # Admin users see all active menus
    if current_user.role_obj and current_user.role_obj.name == "admin":
        menus = query.order_by(Menu.order, Menu.id).all()
    else:
        # Get user's permissions
        user_permissions = set()
        if current_user.role_obj:
            logger.debug(f"User {current_user.email} has role: {current_user.role_obj.name}")
            for role_perm in current_user.role_obj.permissions:
                # role_perm is a RolePermission object, access permission via role_perm.permission
                if role_perm.permission and role_perm.permission.is_active:
                    user_permissions.add(role_perm.permission.code)
                    logger.debug(f"User {current_user.email} has permission: {role_perm.permission.code}")
        
        logger.debug(f"User {current_user.email} permissions: {user_permissions}")
        
        menus = query.order_by(Menu.order, Menu.id).all()
        
        # Filter menus based on permissions
        visible_menus = []
        for menu in menus:
            if not menu.permission_code:
                # Menu without permission requirement is visible to all
                visible_menus.append(menu)
            elif menu.permission_code in user_permissions:
                visible_menus.append(menu)
        menus = visible_menus
    
    # Check if each menu has children and add to response
    menu_responses = []
    for menu in menus:
        # Check if menu has children (for lazy loading)
        has_children = db.query(Menu).filter(
            Menu.parent_id == menu.id,
            Menu.is_active == True
        ).first() is not None
        # Create MenuResponse with has_children field
        menu_response = MenuResponse.model_validate(menu)
        menu_response.has_children = has_children
        menu_responses.append(menu_response)
    
    return menu_responses


@router.get("/menus/{menu_id}", response_model=MenuResponse)
def get_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific menu by ID"""
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    return MenuResponse.model_validate(menu)


@router.post("/menus", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
def create_menu(
    menu: MenuCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new menu (admin only)"""
    # Check if user is admin
    if not current_user.role_obj or current_user.role_obj.name != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create menus")
    
    # Check if code already exists
    existing = db.query(Menu).filter(Menu.code == menu.code).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Menu code already exists")
    
    db_menu = Menu(**menu.model_dump())
    db.add(db_menu)
    db.commit()
    db.refresh(db_menu)
    return MenuResponse.model_validate(db_menu)


@router.put("/menus/{menu_id}", response_model=MenuResponse)
def update_menu(
    menu_id: int,
    menu_update: MenuUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a menu (admin only)"""
    # Check if user is admin
    if not current_user.role_obj or current_user.role_obj.name != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can update menus")
    
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    
    # Check if code already exists (if updating code)
    if menu_update.code and menu_update.code != db_menu.code:
        existing = db.query(Menu).filter(Menu.code == menu_update.code).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Menu code already exists")
    
    # Update fields
    update_data = menu_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_menu, field, value)
    
    db.commit()
    db.refresh(db_menu)
    return MenuResponse.model_validate(db_menu)


@router.delete("/menus/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a menu and all its children recursively (admin only)"""
    # Check if user is admin
    if not current_user.role_obj or current_user.role_obj.name != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can delete menus")
    
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu not found")
    
    # Recursively delete all children
    def delete_children(parent_id: int):
        children = db.query(Menu).filter(Menu.parent_id == parent_id).all()
        for child in children:
            delete_children(child.id)
            db.delete(child)
    
    delete_children(menu_id)
    db.delete(db_menu)
    db.commit()
    return None

