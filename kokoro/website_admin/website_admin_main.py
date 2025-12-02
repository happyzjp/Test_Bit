import logging
import os
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

@app.on_event("startup")
async def startup_event():
    logger.info("Website Admin service starting up")
    from kokoro.website_admin.database import init_data
    try:
        init_data()
    except Exception as e:
        logger.warning(f"Failed to initialize default data: {e}")

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "config_loaded": yaml_config is not None
    }

