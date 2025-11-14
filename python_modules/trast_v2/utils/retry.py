"""Retry utilities and decorators"""

import time
import random
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Retry decorator with exponential backoff
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called on each retry
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.2f}s..."
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, e)
                        except Exception as retry_error:
                            logger.warning(f"Error in on_retry callback: {retry_error}")
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
                    # Add some jitter to avoid thundering herd
                    current_delay += random.uniform(0, 0.5)
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise Exception(f"{func.__name__} failed after {max_attempts} attempts")
        
        return wrapper
    return decorator


def retry_with_exponential_backoff(
    max_attempts: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Retry with exponential backoff and maximum delay cap
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay (seconds)
        max_delay: Maximum delay cap (seconds)
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {current_delay:.2f}s..."
                    )
                    
                    time.sleep(min(current_delay, max_delay))
                    current_delay = min(current_delay * 2, max_delay)
            
            if last_exception:
                raise last_exception
            raise Exception(f"{func.__name__} failed after {max_attempts} attempts")
        
        return wrapper
    return decorator

