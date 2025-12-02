import logging
import sys
from typing import Optional


def setup_logger(name: str, log_level: Optional[str] = None) -> logging.Logger:
    """
    Setup logger with optional log level.
    If log_level is not provided, defaults to INFO to avoid circular import.
    """
    # Lazy import to avoid circular dependency
    if log_level is None:
        try:
            from kokoro.common.config import settings
            log_level = settings.LOG_LEVEL
        except (ImportError, AttributeError):
            log_level = "INFO"  # Default fallback

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level, logging.INFO))
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

