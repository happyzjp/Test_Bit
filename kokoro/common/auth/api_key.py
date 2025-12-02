from fastapi import HTTPException, Security, Request, Depends
from fastapi.security import APIKeyHeader
from typing import Optional, List
from kokoro.common.config import settings, load_yaml_config
from kokoro.common.utils.logging import setup_logger
import os

logger = setup_logger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_auth_instance = None

def get_auth_instance():
    global _auth_instance
    if _auth_instance is None:
        config_path = os.getenv("TASK_CENTER_CONFIG", "config.yml")
        _auth_instance = APIKeyAuth(config_path)
    return _auth_instance


class APIKeyAuth:
    def __init__(self, config_path: Optional[str] = None):
        self.config = load_yaml_config(config_path)
        self.api_keys = self._load_api_keys()
        self.allowed_ips = self._load_allowed_ips()
    
    def _load_api_keys(self) -> set:
        api_keys = set()
        
        if self.config:
            api_key = self.config.get('api.key')
            if api_key:
                api_keys.add(api_key)
        
        env_api_key = os.getenv("TASK_CENTER_API_KEY")
        if env_api_key:
            api_keys.add(env_api_key)
        
        if settings.API_KEY:
            api_keys.add(settings.API_KEY)
        
        if not api_keys:
            logger.warning("No API keys configured, using default key")
            api_keys.add("default_api_key_change_in_production")
        
        return api_keys
    
    def _load_allowed_ips(self) -> List[str]:
        allowed_ips = []
        
        if self.config:
            ips = self.config.get('api.allowed_ips', [])
            if isinstance(ips, list):
                allowed_ips.extend(ips)
        
        env_ips = os.getenv("TASK_CENTER_ALLOWED_IPS", "")
        if env_ips:
            allowed_ips.extend(env_ips.split(","))
        
        return allowed_ips
    
    def verify_ip(self, client_ip: str) -> bool:
        if not self.allowed_ips:
            return True
        
        if client_ip in self.allowed_ips or "127.0.0.1" in client_ip or "localhost" in client_ip:
            return True
        
        return False
    
    def verify(self, api_key: Optional[str] = None) -> bool:
        if not api_key:
            return False
        
        if api_key in self.api_keys:
            return True
        
        return False
    
    def verify_request(
        self,
        request: Request,
        api_key: Optional[str] = None
    ) -> str:
        client_ip = request.client.host if request.client else "unknown"
        
        if not self.verify_ip(client_ip):
            logger.warning(f"Request from unauthorized IP: {client_ip}")
            raise HTTPException(
                status_code=403,
                detail="IP address not allowed"
            )
        
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="API key required. Please provide X-API-Key header."
            )
        
        if not self.verify(api_key):
            logger.warning(f"Invalid API key attempt from {client_ip}: {api_key[:10]}...")
            raise HTTPException(
                status_code=403,
                detail="Invalid API key"
            )
        
        logger.info(f"Authorized request from {client_ip}")
        return api_key


def get_api_key_auth():
    config_path = os.getenv("TASK_CENTER_CONFIG", "config.yml")
    return APIKeyAuth(config_path)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> str:
    auth = get_auth_instance()
    return auth.verify_request(request, api_key)

