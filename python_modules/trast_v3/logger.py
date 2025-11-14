"""Enhanced logging configuration for Trast Parser V3"""

import logging
import os
from datetime import datetime
from pathlib import Path

from config import LOG_DIR

# Global log file path (will be set on first logger creation)
LOG_FILE_PATH = None


def setup_logging(log_name: str = "trast_v3") -> str:
    """
    Setup logging configuration
    
    Args:
        log_name: Base name for log file
    
    Returns:
        Path to log file
    """
    global LOG_FILE_PATH
    
    # Create log file path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOG_FILE_PATH = LOG_DIR / f"{log_name}_{timestamp}.log"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(threadName)s] - [%(name)s] - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE_PATH, encoding="utf-8-sig"),
            logging.StreamHandler()
        ]
    )
    
    # Set specific loggers
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return str(LOG_FILE_PATH)


def get_logger(name: str = None) -> logging.Logger:
    """
    Get logger instance
    
    Args:
        name: Logger name (defaults to module name)
    
    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(f"trast_v3.{name}")
    return logging.getLogger("trast_v3")


def rename_log_file_by_status(status: str, total_products: int = 0):
    """
    Rename log file based on parsing status
    
    Args:
        status: Parsing status ('done', 'insufficient_data', 'error')
        total_products: Total products collected
    """
    global LOG_FILE_PATH
    
    if not LOG_FILE_PATH or not os.path.exists(LOG_FILE_PATH):
        return
    
    try:
        # Determine suffix
        if status == 'done' and total_products >= 100:
            suffix = "_success"
        elif status == 'insufficient_data':
            suffix = "_insufficient_data"
        elif status == 'error':
            suffix = "_failed"
        else:
            suffix = "_unknown"
        
        # Create new path
        base_name = os.path.splitext(LOG_FILE_PATH)[0]
        extension = os.path.splitext(LOG_FILE_PATH)[1]
        new_log_path = f"{base_name}{suffix}{extension}"
        
        # Rename
        os.rename(LOG_FILE_PATH, new_log_path)
        logger = get_logger("logger")
        logger.info(f"Log file renamed: {os.path.basename(new_log_path)}")
        
    except Exception as e:
        logger = get_logger("logger")
        logger.warning(f"Failed to rename log file: {e}")

