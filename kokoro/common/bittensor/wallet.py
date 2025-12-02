import bittensor as bt
from kokoro.common.config import settings
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class WalletManager:
    def __init__(self, wallet_name: str, hotkey_name: str):
        self.wallet_name = wallet_name
        self.hotkey_name = hotkey_name
        self.wallet = bt.wallet(name=wallet_name, hotkey=hotkey_name)
    
    def get_hotkey(self) -> str:
        return self.wallet.hotkey.ss58_address
    
    def get_coldkey(self) -> str:
        return self.wallet.coldkeypub.ss58_address
    
    def get_balance(self) -> float:
        try:
            subtensor = bt.subtensor(network="finney")
            balance = subtensor.get_balance(self.wallet.coldkeypub.ss58_address)
            return float(balance)
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0

