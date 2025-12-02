import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kokoro.website_admin.api import router
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
from kokoro.common.config import settings
from kokoro.common.database.base import Base
from kokoro.common.database import engine

logger = setup_logger(__name__)

app = FastAPI(title="KOKORO Website Admin", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/v1")

# Load configuration
config_path = os.getenv("WEBSITE_ADMIN_CONFIG", "config.yml")
yaml_config = None
if os.path.exists(config_path):
    try:
        yaml_config = YamlConfig(config_path)
        logger.info(f"Config loaded from: {config_path}")
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")

# Configure database URL from config file if provided
if yaml_config:
    database_url = yaml_config.get('database.url', settings.DATABASE_URL)
else:
    database_url = settings.DATABASE_URL

# Update engine URL if different from default
if database_url != settings.DATABASE_URL:
    from kokoro.common.database.session import engine
    # Update engine URL (similar to task_center_main.py)
    engine.url = database_url
    logger.info(f"Database URL configured from config file: {database_url}")
else:
    logger.info(f"Using default database URL: {database_url}")

# Import all models to ensure they are registered with SQLAlchemy
from kokoro.website_admin.models import TaskTemplate, TaskHistory, OperationLog, User
from kokoro.website_admin.models.role import Role, Permission, RolePermission
# Import Task model to ensure it's registered
from kokoro.common.models.task import Task

# Create all database tables on startup
# This will create tables if they don't exist, but won't modify existing tables
Base.metadata.create_all(bind=engine)
logger.info("Database tables checked/created successfully")

@app.on_event("startup")
async def startup_event():
    """Initialize database, run migrations, and default data on startup."""
    logger.info("Website Admin service starting up")
    from kokoro.website_admin.database import init_db, init_data, run_migrations
    
    try:
        # Ensure all database tables are created (including tasks table)
        logger.info("Initializing database tables...")
        init_db()
        logger.info("Database tables initialization completed")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        # Don't raise - allow service to start even if init fails
        # But log the error for debugging
    
    try:
        # Run database migrations
        logger.info("Running database migrations...")
        run_migrations()
        logger.info("Database migrations completed")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        # Don't raise - allow service to start even if migrations fail
        # But log the error for debugging
    
    try:
        # Initialize default data (templates and admin user)
        # This function checks if data already exists before creating
        init_data()
        logger.info("Default data initialization completed")
    except Exception as e:
        logger.warning(f"Failed to initialize default data: {e}")
        # Don't raise - allow service to start even if init fails

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "config_loaded": yaml_config is not None
    }

