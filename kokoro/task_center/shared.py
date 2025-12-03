"""
Shared instances for task center module.
This module stores global instances to avoid circular imports.
"""
from typing import Optional, Any
from kokoro.task_center.services.miner_cache import MinerCache

miner_cache = MinerCache()

bittensor_client: Optional[Any] = None

