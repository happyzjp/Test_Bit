from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

from kokoro.common.database import get_db
from kokoro.website_admin.models.user import User
from kokoro.website_admin.models.role import Role, RolePermission, Permission
from kokoro.website_admin.schemas.auth import (
    UserLogin, UserCreate, UserResponse, TokenResponse, UserUpdate
)
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)

# Default admin email - cannot be deleted
DEFAULT_ADMIN_EMAIL = "admin@kokoro.ai"


def check_admin_permission(current_user: User) -> bool:
    """Check if user has admin role."""
    return current_user.role_obj and current_user.role_obj.name == "admin"

# OAuth2 scheme (for optional OAuth2 compatibility, but we use custom login)
# auto_error=False allows us to handle errors manually in get_current_user
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)

# JWT settings
SECRET_KEY = "your-secret-key-change-in-production"  # TODO: Move to config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        # Ensure password is bytes
        if isinstance(plain_password, str):
            password_bytes = plain_password.encode('utf-8')
        else:
            password_bytes = plain_password
        
        # Bcrypt has a 72 byte limit, truncate if necessary
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        
        # Ensure hashed_password is bytes
        if isinstance(hashed_password, str):
            hash_bytes = hashed_password.encode('utf-8')
        else:
            hash_bytes = hashed_password
        
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception as e:
        logger.error(f"Password verification error: {e}", exc_info=True)
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        # Ensure password is bytes
        if isinstance(password, str):
            password_bytes = password.encode('utf-8')
        else:
            password_bytes = password
        
        # Bcrypt has a 72 byte limit, truncate if necessary
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
            logger.warning("Password truncated to 72 bytes for bcrypt compatibility")
        
        # Generate salt and hash
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        # Return as string
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Password hashing error: {e}", exc_info=True)
        raise


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # If oauth2_scheme didn't extract token, try to get it from Authorization header directly
    if token is None:
        # Fallback: extract token manually from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            logger.debug("Token extracted manually from Authorization header")
        else:
            logger.warning(f"No token provided in request. Authorization header: {auth_header}")
            raise credentials_exception
    
    if not token:
        logger.warning("Token is empty")
        raise credentials_exception
    
    logger.debug(f"Token extracted: {token[:20]}... (length: {len(token)})")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            logger.warning("Token payload missing 'sub' field")
            raise credentials_exception
        user_id = int(user_id_str)
        logger.debug(f"Token decoded successfully, user_id: {user_id}")
    except JWTError as e:
        logger.error(f"JWT decode error: {e}, token: {token[:50]}...")
        raise credentials_exception
    except (ValueError, TypeError) as e:
        logger.error(f"Token user_id conversion error: {e}, user_id_str: {payload.get('sub')}")
        raise credentials_exception
    
    # Eagerly load role and permissions to avoid N+1 queries
    user = db.query(User).options(
        joinedload(User.role_obj).joinedload(Role.permissions).joinedload(RolePermission.permission)
    ).filter(User.id == user_id).first()
    if user is None:
        logger.warning(f"User not found for ID: {user_id}")
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    logger.debug(f"User authenticated: {user.email} (Role: {user.role_obj.name if user.role_obj else 'unknown'})")
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    """Login endpoint."""
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role_obj.name if user.role_obj else "unknown",
            is_active=user.is_active,
            created_at=user.created_at
        )
    )


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register a new user (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create users"
        )
    
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or username already exists"
        )
    
    # Get role by name
    role = db.query(Role).filter(Role.name == user_data.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{user_data.role}' not found"
        )
    
    # Create new user
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        role_id=role.id,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"New user created: {new_user.email} by {current_user.email}")
    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        username=new_user.username,
        role=new_user.role_obj.name if new_user.role_obj else "unknown",
        is_active=new_user.is_active,
        created_at=new_user.created_at
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role_obj.name if current_user.role_obj else "unknown",
        is_active=current_user.is_active,
        avatar=current_user.avatar,
        created_at=current_user.created_at
    )


@router.get("/me/permissions")
async def get_current_user_permissions(current_user: User = Depends(get_current_user)):
    """Get current user permissions."""
    if not current_user.role_obj:
        return {"permissions": []}
    
    permissions = [
        {
            "code": rp.permission.code,
            "name": rp.permission.name,
            "menu_path": rp.permission.menu_path,
            "menu_icon": rp.permission.menu_icon,
            "menu_order": rp.permission.menu_order,
        }
        for rp in current_user.role_obj.permissions
        if rp.permission.is_active
    ]
    
    return {"permissions": sorted(permissions, key=lambda x: x["menu_order"])}


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all users (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list users"
        )
    
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role_obj.name if user.role_obj else "unknown",
            is_active=user.is_active,
            created_at=user.created_at
        )
        for user in users
    ]


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a user (admin only, or self for password)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Only admins can update other users, users can only update their own password
    is_admin = check_admin_permission(current_user)
    if not is_admin and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own password"
        )
    
    # Non-admins can only update password, username, and avatar
    if not is_admin:
        if user_data.password:
            user.hashed_password = get_password_hash(user_data.password)
        if user_data.username:
            user.username = user_data.username
        if user_data.avatar is not None:
            user.avatar = user_data.avatar
        if user_data.password is None and user_data.username is None and user_data.avatar is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your password, username, and avatar"
            )
    else:
        # Admins can update everything
        if user_data.username:
            user.username = user_data.username
        if user_data.password:
            user.hashed_password = get_password_hash(user_data.password)
        if user_data.avatar is not None:
            user.avatar = user_data.avatar
        if user_data.role:
            # Prevent downgrading the default admin to viewer
            if user.email == DEFAULT_ADMIN_EMAIL and user_data.role == "viewer":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change the default admin role to viewer"
                )
            # Get role by name
            new_role = db.query(Role).filter(Role.name == user_data.role).first()
            if not new_role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Role '{user_data.role}' not found"
                )
            user.role_id = new_role.id
        if user_data.is_active is not None:
            # Prevent deactivating the default admin
            if user.email == DEFAULT_ADMIN_EMAIL and user_data.is_active is False:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the default admin user"
                )
            user.is_active = user_data.is_active
    
    db.commit()
    db.refresh(user)
    
    logger.info(f"User updated: {user.email} by {current_user.email}")
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role_obj.name if user.role_obj else "unknown",
        is_active=user.is_active,
        avatar=user.avatar,
        created_at=user.created_at
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a user (admin only)."""
    if not check_admin_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete users"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting the default admin user
    if user.email == DEFAULT_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default admin user"
        )
    
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account"
        )
    
    db.delete(user)
    db.commit()
    
    logger.info(f"User deleted: {user.email} by {current_user.email}")
    return {"message": "User deleted successfully"}

