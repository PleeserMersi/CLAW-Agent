"""
Centralized logging configuration.
Replaces print statements with proper logging.
"""
import logging
import sys
from pathlib import Path


def setup_logging(log_file=None, level=logging.INFO):
    """
    Configure logging with console handler only.
    
    Args:
        log_file: Ignored. File logging is disabled.
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("CLAW-Agent")
    logger.setLevel(level)
    
    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler only (no file logging)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# Create default logger
logger = setup_logging()
