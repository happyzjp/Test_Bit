import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
from kokoro.miner.api import router
from kokoro.miner.services.queue_manager import QueueManager
from kokoro.miner.services.gpu_manager import GPUManager
from kokoro.miner.services.bittensor_sync import BittensorSyncService
from kokoro.common.services.auto_update import AutoUpdateService
from kokoro.common.bittensor.wallet import WalletManager
from kokoro.common.config import settings, load_yaml_config
from kokoro.common.utils.logging import setup_logger
from kokoro.common.utils.thread_pool import get_thread_pool

logger = setup_logger(__name__)

# Add module prefix to logger
for handler in logger.handlers:
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - [MINER] - %(name)s - %(levelname)s - %(message)s'
    ))

config_path = os.getenv("MINER_CONFIG", "config.yml")
yaml_config = load_yaml_config(config_path)

if yaml_config:
    wallet_name = yaml_config.get_wallet_name()
    hotkey_name = yaml_config.get_hotkey_name()
    task_center_url = yaml_config.get_task_center_url()
    gpu_count = yaml_config.get_gpu_count()
    auto_update_config = yaml_config.get_auto_update_config()
else:
    wallet_name = "miner"
    hotkey_name = "default"
    task_center_url = settings.TASK_CENTER_URL
    gpu_count = 1
    auto_update_config = {}

# App will be created after lifespan definition

queue_manager = QueueManager(
    max_queue_size=yaml_config.get('miner.max_queue_size', 100) if yaml_config else 100,
    max_training_jobs=yaml_config.get('miner.max_training_jobs', 2) if yaml_config else 2,
    max_test_jobs=yaml_config.get('miner.max_test_jobs', 4) if yaml_config else 4
)

if yaml_config:
    from kokoro.miner.services.training_service import TrainingService
    training_service = TrainingService(yaml_config)
    queue_manager.training_service = training_service
gpu_manager = GPUManager(gpu_count)
wallet_manager = WalletManager(wallet_name, hotkey_name)
bittensor_sync = BittensorSyncService(wallet_manager)

if yaml_config:
    github_repo = yaml_config.get_github_repo()
    auto_update_enabled = yaml_config.get_auto_update_enabled()
    check_interval = yaml_config.get_auto_update_interval()
else:
    github_repo = settings.GITHUB_REPO
    auto_update_enabled = settings.AUTO_UPDATE_ENABLED
    check_interval = 300

auto_update = AutoUpdateService(
    github_repo=github_repo or "kokoro/miner",
    branch=auto_update_config.get('branch', 'main'),
    check_interval=check_interval,
    restart_delay=auto_update_config.get('restart_delay', 10)
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context: handles startup and shutdown without deprecated on_event."""
    logger.info("Miner service starting up")
    logger.info(f"Miner hotkey: {wallet_manager.get_hotkey()}")
    logger.info(f"Miner balance: {wallet_manager.get_balance()} TAO")
    logger.info(f"Config loaded from: {config_path if yaml_config else 'default'}")
    
    try:
        await queue_manager.start_scheduler()
    except Exception as e:
        logger.error(f"Failed to start queue manager: {e}", exc_info=True)
    
    try:
        await bittensor_sync.start_sync()
    except Exception as e:
        logger.error(f"Failed to start bittensor sync: {e}", exc_info=True)
    
    if auto_update_enabled:
        try:
            await auto_update.start()
        except Exception as e:
            logger.error(f"Failed to start auto-update: {e}", exc_info=True)

    # Yield control to FastAPI (application runs here)
    try:
        yield
    finally:
    logger.info("Miner service shutting down")
    
    try:
        await queue_manager.stop_scheduler()
    except Exception as e:
        logger.error(f"Error stopping queue manager: {e}", exc_info=True)
    
    try:
        await bittensor_sync.stop_sync()
    except Exception as e:
        logger.error(f"Error stopping bittensor sync: {e}", exc_info=True)
    
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
app = FastAPI(title="KOKORO Miner", version="1.0.0", lifespan=lifespan)
app.include_router(router, prefix="/v1")

@app.get("/health")
async def health_check():
    try:
        return {
            "status": "ok",
            "hotkey": wallet_manager.get_hotkey(),
            "balance": wallet_manager.get_balance(),
            "queue_length": queue_manager.get_queue_length(),
            "available_gpus": gpu_manager.get_available_gpu_count(),
            "stake": bittensor_sync.get_stake()
        }
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    
    # Get host and port from environment variables or use defaults
    host = os.getenv("MINER_HOST", "0.0.0.0")
    port = int(os.getenv("MINER_PORT", "8001"))
    
    logger.info(f"Starting Miner service on {host}:{port}")
    logger.info("Using asyncio event loop (required for bittensor compatibility)")
    
    # Run uvicorn with asyncio loop (required for bittensor)
    uvicorn.run(
        app,
        host=host,
        port=port,
        loop="asyncio",  # Force asyncio loop instead of uvloop
        log_level="info"
    )
