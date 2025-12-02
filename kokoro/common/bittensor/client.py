# Check if uvloop is being used (bittensor doesn't support uvloop)
import sys
try:
    import asyncio
    loop = asyncio.get_event_loop()
    if hasattr(loop, '__class__') and 'uvloop' in str(type(loop)):
        raise RuntimeError(
            "uvloop is not compatible with bittensor. "
            "Please run uvicorn with --loop asyncio flag: "
            "uvicorn kokoro.task_center.task_center_main:app --host 0.0.0.0 --port 8000 --loop asyncio"
        )
except RuntimeError:
    # No event loop running yet, which is fine
    pass

# Fix pandas compatibility issue with bittensor
# pandas 2.0+ removed pandas.io.json.json_normalize, moved to pandas.json_normalize
# This must be done before importing bittensor
try:
    import pandas as pd
    # Check if pandas.io.json.json_normalize exists
    if not hasattr(pd.io.json, 'json_normalize'):
        # Monkey patch for pandas 2.0+ compatibility
        try:
            from pandas import json_normalize
            pd.io.json.json_normalize = json_normalize
        except ImportError:
            # Fallback: try to create a wrapper
            try:
                from pandas import json_normalize as _json_normalize
                def _wrapper(*args, **kwargs):
                    return _json_normalize(*args, **kwargs)
                pd.io.json.json_normalize = _wrapper
            except ImportError:
                pass
except (ImportError, AttributeError):
    pass

import bittensor as bt
from typing import Dict, List, Optional
from kokoro.common.config import settings, load_yaml_config
from kokoro.common.utils.logging import setup_logger
from kokoro.common.utils.retry import retry_sync_with_backoff

logger = setup_logger(__name__)


class BittensorClient:
    def __init__(self, wallet_name: str, hotkey_name: str):
        try:
            # Load network configuration from YAML if available, otherwise fall back to Settings
            yaml_config = load_yaml_config()
            if yaml_config:
                chain_endpoint = yaml_config.get('bittensor.chain_endpoint', settings.BITNETWORK_CHAIN_ENDPOINT)
                network = yaml_config.get('bittensor.network', settings.BITNETWORK_NETWORK)
                netuid = yaml_config.get('bittensor.netuid', settings.BITNETWORK_NETUID)
            else:
                chain_endpoint = settings.BITNETWORK_CHAIN_ENDPOINT
                netuid = settings.BITNETWORK_NETUID
                network = settings.BITNETWORK_NETWORK

            self.wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
            self.subtensor = bt.subtensor(network=network or "finney")
            self.netuid = netuid
            self.metagraph = None
            self._sync_lock = False
            # Try to sync metagraph, but don't fail if network is unavailable
            try:
                self.sync_metagraph()
            except Exception as e:
                logger.warning(f"Failed to sync metagraph on initialization (network may be unavailable): {e}")
        except Exception as e:
            logger.error(f"Failed to initialize BittensorClient: {e}", exc_info=True)
            # Don't raise - allow service to start even if bittensor connection fails
            # This is useful for local development
            self.wallet = None
            self.subtensor = None
            self.metagraph = None
            self._sync_lock = False
    
    @retry_sync_with_backoff(max_retries=3, initial_delay=2.0, max_delay=30.0)
    def sync_metagraph(self):
        # If subtensor is not initialized (e.g. connection refused), skip syncing
        if self.subtensor is None:
            logger.warning("Subtensor is not initialized; skipping metagraph sync")
            return

        if self._sync_lock:
            logger.warning("Metagraph sync already in progress")
            return
        
        try:
            self._sync_lock = True
            self.metagraph = self.subtensor.metagraph(netuid=self.netuid)
            logger.info(f"Metagraph synced: {len(self.metagraph.hotkeys)} neurons")
        except Exception as e:
            logger.error(f"Failed to sync metagraph: {e}", exc_info=True)
            raise
        finally:
            self._sync_lock = False
    
    def get_miner_stake(self, hotkey: str) -> float:
        if not self.metagraph:
            try:
                self.sync_metagraph()
            except Exception as e:
                logger.error(f"Failed to sync metagraph for stake query: {e}")
                return 0.0
        
        try:
            uid = self.metagraph.hotkeys.index(hotkey)
            stake = float(self.metagraph.S[uid])
            return stake
        except (ValueError, IndexError) as e:
            logger.warning(f"Hotkey {hotkey} not found in metagraph: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get miner stake: {e}", exc_info=True)
            return 0.0
    
    def get_validator_stake(self, hotkey: str) -> float:
        return self.get_miner_stake(hotkey)
    
    def get_all_miners(self) -> List[Dict]:
        if not self.metagraph:
            try:
                self.sync_metagraph()
            except Exception as e:
                logger.error(f"Failed to sync metagraph for miners query: {e}")
                return []
        
        try:
            miners = []
            for uid in range(len(self.metagraph.hotkeys)):
                try:
                    axon = self.metagraph.axons[uid] if uid < len(self.metagraph.axons) else None
                    miners.append({
                        "uid": uid,
                        "hotkey": self.metagraph.hotkeys[uid],
                        "stake": float(self.metagraph.S[uid]),
                        "is_active": axon.ip != "0.0.0.0" if axon else False,
                        "axon": axon
                    })
                except Exception as e:
                    logger.warning(f"Failed to process miner {uid}: {e}")
                    continue
            
            return miners
        except Exception as e:
            logger.error(f"Failed to get all miners: {e}", exc_info=True)
            return []
    
    def set_weights(
        self,
        uids: List[int],
        weights: List[float]
    ):
        try:
            if not uids or not weights:
                logger.warning("Empty uids or weights provided")
                return
            
            if len(uids) != len(weights):
                raise ValueError(f"Uids length ({len(uids)}) != weights length ({len(weights)})")
            
            self.subtensor.set_weights(
                netuid=self.netuid,
                wallet=self.wallet,
                uids=uids,
                weights=weights
            )
            logger.info(f"Weights set successfully: {len(uids)} miners")
        except Exception as e:
            logger.error(f"Failed to set weights: {e}", exc_info=True)
            raise
    
    def get_emission(self) -> float:
        try:
            emission = self.subtensor.get_emission(netuid=self.netuid)
            return float(emission)
        except Exception as e:
            logger.error(f"Failed to get emission: {e}", exc_info=True)
            return 0.0
