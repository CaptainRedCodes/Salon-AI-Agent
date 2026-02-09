"""
Centralized logging configuration for the Salon AI Agent.

Import this module at the top of any file that needs logging.
This replaces scattered logging.basicConfig() calls throughout the codebase.
"""
import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure logging for the entire application.
    
    Should be called once at application startup (main.py or entrypoint.py).
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Usage:
        from app.core.logging_config import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)



setup_logging()
