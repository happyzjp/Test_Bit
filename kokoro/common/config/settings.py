from pydantic_settings import BaseSettings
from typing import Optional
from kokoro.common.config.yaml_config import YamlConfig
import os

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://kokoro:kokoro@localhost:5432/kokoro"
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    
    BITNETWORK_NETUID: int = 119
    BITNETWORK_NETWORK: str = 'finney'
    BITNETWORK_CHAIN_ENDPOINT: str = "wss://entrypoint-finney.opentensor.ai:443"
    
    TASK_CENTER_URL: str = "http://localhost:8000"
    
    API_KEY: Optional[str] = None
    
    LOG_LEVEL: str = "INFO"
    
    GITHUB_REPO: Optional[str] = None
    AUTO_UPDATE_ENABLED: bool = False
    
    MINER_MIN_STAKE: float = 1000.0
    
    CONFIG_FILE: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

def load_yaml_config(config_path: Optional[str] = None) -> Optional[YamlConfig]:
    if config_path:
        if os.path.exists(config_path):
            return YamlConfig(config_path)
    
    default_paths = [
        "config.yml",
        "config.yaml",
        "config/config.yml",
        "config/config.yaml"
    ]
    
    for path in default_paths:
        if os.path.exists(path):
            return YamlConfig(path)
    
    return None

