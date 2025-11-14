"""Logging configuration for Trast Parser V2"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from config import LOG_DIR

# Create log file with timestamp
LOG_FILE = LOG_DIR / f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure root logger
logger = logging.getLogger("trast_v2")
logger.setLevel(logging.DEBUG)

# Prevent duplicate handlers
if logger.handlers:
    logger.handlers.clear()

# File handler
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8-sig")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter(
    '%(asctime)s - [%(threadName)s] - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(file_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter(
    '%(asctime)s - [%(threadName)s] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(console_formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Set levels for third-party loggers
logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance"""
    if name:
        return logging.getLogger(f"trast_v2.{name}")
    return logger


def rename_log_file_by_status(status: str, total_products: int = 0):
    """Rename log file based on execution status"""
    try:
        if not LOG_FILE.exists():
            return
        
        # Determine suffix
        if status == 'done' and total_products >= 100:
            suffix = "_success"
        elif status == 'insufficient_data':
            suffix = "_insufficient_data"
        elif status == 'error':
            suffix = "_failed"
        else:
            suffix = "_unknown"
        
        # Create new name
        base_name = LOG_FILE.stem
        extension = LOG_FILE.suffix
        new_log_path = LOG_FILE.parent / f"{base_name}{suffix}{extension}"
        
        # Rename
        LOG_FILE.rename(new_log_path)
        logger.info(f"Log file renamed: {new_log_path.name}")
    except Exception as e:
        logger.warning(f"Failed to rename log file: {e}")

