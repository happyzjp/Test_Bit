import asyncio
import logging
import os
import sys

# Force use of asyncio event loop instead of uvloop
# bittensor library doesn't support uvloop, so we need to use standard asyncio
# This must be done before importing bittensor
if 'uvloop' in sys.modules:
    # If uvloop is already imported, we can't change it
    # User must use --loop asyncio flag with uvicorn
    pass
else:
    # Try to prevent uvloop from being used
    os.environ.setdefault("UVLOOP_DISABLED", "1")

# Fix pandas compatibility issue with bittensor
# pandas 2.0+ removed pandas.io.json.json_normalize, moved to pandas.json_normalize
# This must be done before importing bittensor
try:
    import pandas as pd
    if not hasattr(pd.io.json, 'json_normalize'):
        # Monkey patch for pandas 2.0+ compatibility
        try:
            from pandas import json_normalize
            pd.io.json.json_normalize = json_normalize
        except ImportError:
            pass
except (ImportError, AttributeError):
    pass

from fastapi import FastAPI
from contextlib import asynccontextmanager
from kokoro.task_center.api import router
from kokoro.common.database.base import Base
from kokoro.common.database import engine
from kokoro.common.services.auto_update import AutoUpdateService
from kokoro.common.bittensor.client import BittensorClient
from kokoro.common.config import settings, load_yaml_config
from kokoro.common.utils.logging import setup_logger
from kokoro.common.database import SessionLocal
from kokoro.task_center.services.task_lifecycle_manager import TaskLifecycleManager
from kokoro.task_center.services.miner_health_checker import MinerHealthChecker
from kokoro.common.bittensor.wallet import WalletManager
from kokoro.common.utils.thread_pool import get_thread_pool
from kokoro.task_center.shared import miner_cache

logger = setup_logger(__name__)

# Add module prefix to logger
for handler in logger.handlers:
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - [TASK_CENTER] - %(name)s - %(levelname)s - %(message)s'
    ))

from kokoro.website_admin.models import TaskTemplate, TaskHistory, OperationLog
from kokoro.common.models.miner import Miner

Base.metadata.create_all(bind=engine)

config_path = os.getenv("TASK_CENTER_CONFIG", "config.yml")
yaml_config = load_yaml_config(config_path)

if yaml_config:
    wallet_name = yaml_config.get('wallet.name', 'task_center')
    hotkey_name = yaml_config.get('wallet.hotkey', 'default')
    auto_update_config = yaml_config.get_auto_update_config()
    database_url = yaml_config.get('database.url', settings.DATABASE_URL)
else:
    wallet_name = "task_center"
    hotkey_name = "default"
    auto_update_config = {}
    database_url = settings.DATABASE_URL

if database_url != settings.DATABASE_URL:
    from kokoro.common.database.session import engine
    engine.url = database_url

app = FastAPI(title="KOKORO Task Center", version="1.0.0")

app.include_router(router, prefix="/v1")

# Initialize bittensor client (may fail if network unavailable, but service can still start)
try:
    bittensor_client = BittensorClient(wallet_name, hotkey_name)
except Exception as e:
    logger.warning(f"Bittensor client initialization failed (service will continue): {e}")
    bittensor_client = None

task_center_wallet_manager = WalletManager(wallet_name, hotkey_name)

if yaml_config:
    github_repo = yaml_config.get_github_repo()
    auto_update_enabled = yaml_config.get_auto_update_enabled()
    check_interval = yaml_config.get_auto_update_interval()
else:
    github_repo = settings.GITHUB_REPO
    auto_update_enabled = settings.AUTO_UPDATE_ENABLED
    check_interval = 300

auto_update = AutoUpdateService(
    github_repo=github_repo or "kokoro/task_center",
    branch=auto_update_config.get('branch', 'main'),
    check_interval=check_interval,
    restart_delay=auto_update_config.get('restart_delay', 10)
)

lifecycle_manager = None
miner_health_checker = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context: handles startup and shutdown without deprecated on_event."""
    global lifecycle_manager, miner_health_checker

    # Startup logic
    logger.info("Task Center service starting up")
    logger.info(f"Config loaded from: {config_path if yaml_config else 'default'}")

    if bittensor_client:
        try:
            bittensor_client.sync_metagraph()
        except Exception as e:
            logger.warning(f"Failed to sync metagraph (network may be unavailable): {e}")
    else:
        logger.warning("Bittensor client not available - some features may be limited")

    try:
        db = SessionLocal()
        lifecycle_manager = TaskLifecycleManager(db)
        await lifecycle_manager.start()
        logger.info("Task lifecycle manager started")
    except Exception as e:
        logger.error(f"Failed to start task lifecycle manager: {e}", exc_info=True)

    try:
        db = SessionLocal()
        check_interval = yaml_config.get('task_center.miner_health_check_interval', 600) if yaml_config else 600
        heartbeat_timeout = yaml_config.get('task_center.miner_heartbeat_timeout', 120) if yaml_config else 120
        miner_health_checker = MinerHealthChecker(
            db,
            task_center_wallet_manager,
            miner_cache,
            check_interval=check_interval,
            heartbeat_timeout=heartbeat_timeout
        )
        await miner_health_checker.start()
        logger.info("Miner health checker started")
    except Exception as e:
        logger.error(f"Failed to start miner health checker: {e}", exc_info=True)

    if auto_update_enabled:
        try:
            await auto_update.start()
        except Exception as e:
            logger.error(f"Failed to start auto-update: {e}", exc_info=True)

    # Yield control to FastAPI (application runs here)
    try:
        yield
    finally:
        # Shutdown logic
        logger.info("Task Center service shutting down")

        if lifecycle_manager:
            try:
                await lifecycle_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping lifecycle manager: {e}", exc_info=True)

        if miner_health_checker:
            try:
                await miner_health_checker.stop()
            except Exception as e:
                logger.error(f"Error stopping miner health checker: {e}", exc_info=True)

        try:
            await auto_update.stop()
        except Exception as e:
            logger.error(f"Error stopping auto-update: {e}", exc_info=True)

        try:
            thread_pool = get_thread_pool()
            thread_pool.shutdown(wait=True)
        except Exception as e:
            logger.error(f"Error shutting down thread pool: {e}", exc_info=True)


# Recreate app with lifespan handler to avoid on_event deprecation warnings
app = FastAPI(title="KOKORO Task Center", version="1.0.0", lifespan=lifespan)
app.include_router(router, prefix="/v1")

@app.get("/health")
async def health_check():
    try:
        miners_count = 0
        if bittensor_client and bittensor_client.metagraph:
            try:
                miners_count = len(bittensor_client.get_all_miners())
            except Exception:
                pass
        
        return {
            "status": "ok",
            "miners_count": miners_count,
            "online_miners": miner_cache.get_online_count(),
            "cache_size": miner_cache.get_cache_size(),
            "last_update": miner_cache.get_last_update().isoformat() if miner_cache.get_last_update() else None,
            "bittensor_connected": bittensor_client is not None and bittensor_client.metagraph is not None
        }
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("TASK_CENTER_HOST", "0.0.0.0")
    port = int(os.getenv("TASK_CENTER_PORT", "8000"))
    
    logger.info(f"Starting Task Center service on {host}:{port}")
    logger.info("Using asyncio event loop (required for bittensor compatibility)")
    
    # Run uvicorn with asyncio loop (required for bittensor)
    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="asyncio",  # Force asyncio loop instead of uvloop
        log_level="info"
    )

