from fastapi import APIRouter
from kokoro.miner.services.queue_manager import QueueManager
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)
queue_manager = QueueManager()


@router.get("/status")
async def get_queue_status():
    stats = queue_manager.get_queue_stats()
    return stats

