import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kokoro.website_admin.api import router
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
from kokoro.common.database.base import Base
from kokoro.common.database import engine

logger = setup_logger(__name__)

# Add module prefix to logger
for handler in logger.handlers:
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - [WEBSITE_ADMIN] - %(name)s - %(levelname)s - %(message)s'
    ))

# App will be created after lifespan definition

config_path = os.getenv("WEBSITE_ADMIN_CONFIG", "config.yml")
yaml_config = None
if os.path.exists(config_path):
    try:
        yaml_config = YamlConfig(config_path)
        logger.info(f"Config loaded from: {config_path}")
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")

from kokoro.website_admin.models import TaskTemplate, TaskHistory, OperationLog, User

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context: handles startup and shutdown without deprecated on_event."""
    logger.info("Website Admin service starting up")
    from kokoro.website_admin.database import init_data
    try:
        init_data()
    except Exception as e:
        logger.warning(f"Failed to initialize default data: {e}")
    
    # Yield control to FastAPI (application runs here)
    yield

# Recreate app with lifespan handler to avoid on_event deprecation warnings
app = FastAPI(title="KOKORO Website Admin", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/v1")

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "config_loaded": yaml_config is not None
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("WEBSITE_ADMIN_HOST", "0.0.0.0")
    port = int(os.getenv("WEBSITE_ADMIN_PORT", "8003"))
    
    logger.info(f"Starting Website Admin service on {host}:{port}")
    logger.info("Using asyncio event loop (required for bittensor compatibility)")
    
    # Run uvicorn with asyncio loop (required for bittensor)
    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="asyncio",  # Force asyncio loop instead of uvloop
        log_level="info"
    )
