from kokoro.common.database.base import Base
from kokoro.common.database import engine, SessionLocal
from kokoro.website_admin.models import TaskTemplate, TaskHistory, OperationLog, User
from kokoro.website_admin.models.role import Role, Permission, RolePermission
from kokoro.website_admin.models.menu import Menu
from kokoro.website_admin.api.auth import get_password_hash
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


def init_db():
    # Import all models to ensure they are registered with SQLAlchemy Base metadata
    from kokoro.website_admin.models import TaskTemplate, TaskHistory, OperationLog, User
    from kokoro.website_admin.models.role import Role, Permission, RolePermission
    from kokoro.website_admin.models.menu import Menu
    # Import Task model from common models to ensure tasks table is created
    from kokoro.common.models.task import Task
    
    Base.metadata.create_all(bind=engine)
    logger.info("Website admin database tables created successfully (including tasks table)")


def init_data():
    db = SessionLocal()
    try:
        default_templates = [
            {
                "name": "text_lora_new_default",
                "description": "Default template for new text LoRA training",
                "workflow_type": "text_lora_creation",
                "workflow_spec": {
                    "theme": "japanese_culture_chat",
                    "target_platform": "mobile",
                    "deployment_target": "mobile_app",
                    "training_mode": "new",
                    "dataset_spec": {
                        "source": "huggingface",
                        "repository_id": "kokoro/japanese-culture-qa-dataset",
                        "sample_count": 2000,
                        "data_format": "jsonl",
                        "question_column": "question",
                        "answer_column": "answer"
                    },
                    "training_spec": {
                        "base_model": "Qwen/Qwen3-0.6B",
                        "lora_rank": 16,
                        "lora_alpha": 32,
                        "iteration_count": 1000,
                        "batch_size": 4,
                        "learning_rate": 2e-4,
                        "max_length": 512
                    }
                },
                "announcement_duration": "0.25",
                "execution_duration": "3.0",
                "review_duration": "1.0",
                "reward_duration": "0.0"
            },
            {
                "name": "text_lora_incremental_default",
                "description": "Default template for incremental text LoRA training",
                "workflow_type": "text_lora_creation",
                "workflow_spec": {
                    "theme": "japanese_culture_chat",
                    "target_platform": "mobile",
                    "deployment_target": "mobile_app",
                    "training_mode": "incremental",
                    "dataset_spec": {
                        "source": "huggingface",
                        "repository_id": "kokoro/japanese-culture-qa-dataset-v2",
                        "sample_count": 1500,
                        "data_format": "jsonl",
                        "question_column": "question",
                        "answer_column": "answer"
                    },
                    "training_spec": {
                        "base_model": "Qwen/Qwen3-0.6B",
                        "lora_rank": 16,
                        "lora_alpha": 32,
                        "iteration_count": 800,
                        "batch_size": 4,
                        "learning_rate": 1e-4,
                        "max_length": 512
                    }
                },
                "announcement_duration": "0.25",
                "execution_duration": "3.0",
                "review_duration": "1.0",
                "reward_duration": "0.0"
            },
            {
                "name": "image_lora_new_default",
                "description": "Default template for new image LoRA training",
                "workflow_type": "image_lora_creation",
                "workflow_spec": {
                    "theme": "manga_style",
                    "target_platform": "executor",
                    "deployment_target": "executor_node",
                    "training_mode": "new",
                    "dataset_spec": {
                        "source": "huggingface",
                        "repository_id": "kokoro/manga-style-dataset",
                        "sample_count": 200,
                        "image_column": "image",
                        "caption_column": "text"
                    },
                    "training_spec": {
                        "base_model": "black-forest-labs/FLUX.1-dev",
                        "lora_rank": 16,
                        "lora_alpha": 32,
                        "iteration_count": 1000,
                        "batch_size": 2,
                        "learning_rate": 1e-4,
                        "resolution": [512, 768]
                    }
                },
                "announcement_duration": "0.25",
                "execution_duration": "3.0",
                "review_duration": "1.0",
                "reward_duration": "0.0"
            },
            {
                "name": "image_lora_incremental_default",
                "description": "Default template for incremental image LoRA training",
                "workflow_type": "image_lora_creation",
                "workflow_spec": {
                    "theme": "manga_style",
                    "target_platform": "executor",
                    "deployment_target": "executor_node",
                    "training_mode": "incremental",
                    "dataset_spec": {
                        "source": "huggingface",
                        "repository_id": "kokoro/manga-style-dataset-v2",
                        "sample_count": 150,
                        "image_column": "image",
                        "caption_column": "text"
                    },
                    "training_spec": {
                        "base_model": "black-forest-labs/FLUX.1-dev",
                        "lora_rank": 16,
                        "lora_alpha": 32,
                        "iteration_count": 800,
                        "batch_size": 2,
                        "learning_rate": 5e-5,
                        "resolution": [512, 768]
                    }
                },
                "announcement_duration": "0.25",
                "execution_duration": "3.0",
                "review_duration": "1.0",
                "reward_duration": "0.0"
            }
        ]
        
        for template_data in default_templates:
            existing = db.query(TaskTemplate).filter(
                TaskTemplate.name == template_data["name"]
            ).first()
            
            if not existing:
                template = TaskTemplate(**template_data)
                db.add(template)
                logger.info(f"Created default template: {template_data['name']}")
        
        db.commit()
        logger.info("Default task templates initialized successfully")
        
        # Initialize default permissions (menus)
        default_permissions = [
            {"code": "dashboard", "name": "Dashboard", "menu_path": "/dashboard", "menu_icon": "LayoutDashboard", "menu_order": 1},
            {"code": "tasks", "name": "Tasks & Workflows", "menu_path": "/tasks", "menu_icon": "ListTodo", "menu_order": 2},
            {"code": "create_task", "name": "Create Task", "menu_path": "/create-task", "menu_icon": "PlusCircle", "menu_order": 3},
            {"code": "miners", "name": "Miners", "menu_path": "/miners", "menu_icon": "Users", "menu_order": 4},
            {"code": "validators", "name": "Validators", "menu_path": "/validators", "menu_icon": "Network", "menu_order": 5},
            {"code": "users", "name": "User Management", "menu_path": "/users", "menu_icon": "Shield", "menu_order": 6},
            {"code": "roles", "name": "Role Management", "menu_path": "/roles", "menu_icon": "Shield", "menu_order": 7},
            {"code": "api_keys", "name": "API Keys", "menu_path": "/api-keys", "menu_icon": "Key", "menu_order": 8},
            {"code": "governance", "name": "Governance", "menu_path": "/governance", "menu_icon": "Settings", "menu_order": 9},
        ]
        
        created_permissions = {}
        for perm_data in default_permissions:
            existing_perm = db.query(Permission).filter(Permission.code == perm_data["code"]).first()
            if not existing_perm:
                permission = Permission(**perm_data)
                db.add(permission)
                db.flush()
                created_permissions[perm_data["code"]] = permission
                logger.info(f"Created permission: {perm_data['name']}")
            else:
                created_permissions[perm_data["code"]] = existing_perm
        
        db.commit()
        logger.info("Default permissions initialized successfully")
        
        # Initialize default roles
        # Admin role - has all permissions
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            admin_role = Role(
                name="admin",
                description="System administrator with full access",
                is_system=True,
                is_active=True
            )
            db.add(admin_role)
            db.flush()
            
            # Assign all permissions to admin role
            for perm in created_permissions.values():
                role_perm = RolePermission(role_id=admin_role.id, permission_id=perm.id)
                db.add(role_perm)
            
            logger.info("Created admin role with all permissions")
        else:
            # Ensure admin has all permissions
            existing_perm_ids = {rp.permission_id for rp in admin_role.permissions}
            for perm in created_permissions.values():
                if perm.id not in existing_perm_ids:
                    role_perm = RolePermission(role_id=admin_role.id, permission_id=perm.id)
                    db.add(role_perm)
        
        # Viewer role - limited permissions
        viewer_role = db.query(Role).filter(Role.name == "viewer").first()
        if not viewer_role:
            viewer_role = Role(
                name="viewer",
                description="View-only access to basic features",
                is_system=True,
                is_active=True
            )
            db.add(viewer_role)
            db.flush()
            
            # Assign limited permissions to viewer role
            viewer_permissions = ["dashboard", "tasks", "miners", "validators", "governance"]
            for perm_code in viewer_permissions:
                if perm_code in created_permissions:
                    perm = created_permissions[perm_code]
                    role_perm = RolePermission(role_id=viewer_role.id, permission_id=perm.id)
                    db.add(role_perm)
            
            logger.info("Created viewer role with limited permissions")
        
        db.commit()
        logger.info("Default roles initialized successfully")
        
        # Initialize default menus in tree structure
        # Level 1: Root menus (Dashboard, Tasks & Workflows, Network, System)
        level1_menus = [
            {"code": "dashboard", "name": "Dashboard", "path": "/dashboard", "icon": "LayoutDashboard", "order": 1},
            {"code": "overview", "name": "Tasks & Workflows", "path": "#", "icon": "ListTodo", "order": 2},
            {"code": "network", "name": "Network", "path": "#", "icon": "Network", "order": 3},
            {"code": "system", "name": "System", "path": "#", "icon": "Settings", "order": 4},
        ]
        
        created_menus = {}
        
        # Create or update level 1 menus
        for menu_data in level1_menus:
            existing_menu = db.query(Menu).filter(Menu.code == menu_data["code"]).first()
            if not existing_menu:
                menu = Menu(**menu_data)
                db.add(menu)
                db.flush()
                created_menus[menu_data["code"]] = menu
                logger.info(f"Created level 1 menu: {menu_data['name']}")
            else:
                # Update existing menu properties if changed
                updated = False
                if existing_menu.name != menu_data["name"]:
                    existing_menu.name = menu_data["name"]
                    updated = True
                if existing_menu.path != menu_data["path"]:
                    existing_menu.path = menu_data["path"]
                    updated = True
                if existing_menu.order != menu_data["order"]:
                    existing_menu.order = menu_data["order"]
                    updated = True
                if existing_menu.icon != menu_data["icon"]:
                    existing_menu.icon = menu_data["icon"]
                    updated = True
                # If this was a child menu, make it a root menu
                if existing_menu.parent_id is not None:
                    existing_menu.parent_id = None
                    updated = True
                if updated:
                    logger.info(f"Updated level 1 menu: {menu_data['code']} -> {menu_data['name']}")
                created_menus[menu_data["code"]] = existing_menu
        
        db.commit()
        
        # Level 2: Sub-menus under Tasks & Workflows
        # First menu should be Task List (order: 1)
        overview_menus = [
            {"code": "tasks", "name": "Task List", "path": "/tasks", "icon": "ListTodo", "order": 1, "permission_code": "tasks", "parent_code": "overview"},
            {"code": "create_task", "name": "Create Task", "path": "/create-task", "icon": "PlusCircle", "order": 2, "permission_code": "create_task", "parent_code": "overview"},
        ]
        
        # Level 2: Sub-menus under Network
        network_menus = [
            {"code": "miners", "name": "Miners", "path": "/miners", "icon": "Users", "order": 1, "permission_code": "miners", "parent_code": "network"},
            {"code": "validators", "name": "Validators", "path": "/validators", "icon": "Network", "order": 2, "permission_code": "validators", "parent_code": "network"},
        ]
        
        # Level 2: Sub-menus under System
        system_menus = [
            {"code": "users", "name": "User Management", "path": "/users", "icon": "Shield", "order": 1, "permission_code": "users", "parent_code": "system"},
            {"code": "roles", "name": "Role Management", "path": "/roles", "icon": "Shield", "order": 2, "permission_code": "roles", "parent_code": "system"},
            {"code": "menus", "name": "Menu Management", "path": "/menus", "icon": "Menu", "order": 3, "permission_code": "menus", "parent_code": "system"},
            {"code": "api_keys", "name": "API Keys", "path": "/api-keys", "icon": "Key", "order": 4, "permission_code": "api_keys", "parent_code": "system"},
            {"code": "governance", "name": "Governance", "path": "/governance", "icon": "Settings", "order": 5, "permission_code": "governance", "parent_code": "system"},
        ]
        
        # Create or update level 2 menus
        all_level2_menus = overview_menus + network_menus + system_menus
        for menu_data in all_level2_menus:
            parent_code = menu_data.get("parent_code")
            existing_menu = db.query(Menu).filter(Menu.code == menu_data["code"]).first()
            if not existing_menu:
                parent_menu = created_menus.get(parent_code)
                if parent_menu:
                    menu_data_copy = menu_data.copy()
                    menu_data_copy.pop("parent_code")
                    menu_data_copy["parent_id"] = parent_menu.id
                    menu = Menu(**menu_data_copy)
                    db.add(menu)
                    db.flush()
                    created_menus[menu_data["code"]] = menu
                    logger.info(f"Created level 2 menu: {menu_data['name']} under {parent_menu.name}")
            else:
                # Update existing menu order and name if changed
                parent_menu = created_menus.get(parent_code)
                if parent_menu:
                    if existing_menu.parent_id != parent_menu.id:
                        existing_menu.parent_id = parent_menu.id
                        logger.info(f"Updated level 2 menu parent: {menu_data['code']} -> {parent_menu.name}")
                    if existing_menu.order != menu_data["order"]:
                        existing_menu.order = menu_data["order"]
                        logger.info(f"Updated level 2 menu order: {menu_data['code']} -> {menu_data['order']}")
                    if existing_menu.name != menu_data["name"]:
                        existing_menu.name = menu_data["name"]
                        logger.info(f"Updated level 2 menu name: {menu_data['code']} -> {menu_data['name']}")
                created_menus[menu_data["code"]] = existing_menu
        
        db.commit()
        
        # Remove Dashboard from Tasks & Workflows if it exists as a child menu
        # (Dashboard is now a level 1 menu)
        dashboard_as_child = db.query(Menu).filter(
            Menu.code == "dashboard",
            Menu.parent_id.isnot(None)
        ).first()
        if dashboard_as_child:
            # Delete the child dashboard menu if it exists
            db.delete(dashboard_as_child)
            db.commit()
            logger.info("Removed Dashboard from Tasks & Workflows (now a level 1 menu)")
        
        logger.info("Default menus initialized successfully")
        
        # Create default admin user if not exists
        admin_user = db.query(User).filter(User.email == "admin@kokoro.ai").first()
        if not admin_user:
            admin_user = User(
                email="admin@kokoro.ai",
                username="admin",
                hashed_password=get_password_hash("password"),
                role_id=admin_role.id,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            logger.info("Default admin user created: admin@kokoro.ai / password")
        
    except Exception as e:
        logger.error(f"Failed to initialize default data: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
    init_data()
    print("Website admin database initialized successfully")
