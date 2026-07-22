"""
Centralized logging configuration.
Replaces print statements with proper logging.
"""
import logging
import sys
from pathlib import Path


def setup_logging(log_file=None, level=logging.INFO):
    """
    Configure logging with both file and console handlers.
    
    Args:
        log_file: Optional path to log file. If None, uses default location.
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
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# Create default logger
logger = setup_logging()
