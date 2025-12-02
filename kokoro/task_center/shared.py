"""
Shared instances for task center module.
This module stores global instances to avoid circular imports.
"""
from kokoro.task_center.services.miner_cache import MinerCache

# Global miner cache instance
miner_cache = MinerCache()

