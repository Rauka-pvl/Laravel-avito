"""Enhanced retry utilities with exponential backoff for Trast Parser V3"""

import time
import random
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional, Any

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
    jitter: bool = True
):
    """
    Enhanced retry decorator with exponential backoff and jitter
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        max_delay: Maximum delay cap (seconds)
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called on each retry (attempt, exception)
        jitter: Add random jitter to avoid thundering herd
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    
                    # Calculate delay with backoff
                    actual_delay = min(current_delay, max_delay)
                    if jitter:
                        actual_delay += random.uniform(0, actual_delay * 0.1)
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                        f"Retrying in {actual_delay:.2f}s..."
                    )
                    
                    if on_retry:
                        try:
                            on_retry(attempt, e, actual_delay)
                        except Exception as retry_error:
                            logger.warning(f"Error in on_retry callback: {retry_error}")
                    
                    time.sleep(actual_delay)
                    current_delay = min(current_delay * backoff, max_delay)
            
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
    jitter: bool = True
):
    """
    Retry with exponential backoff and maximum delay cap
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay (seconds)
        max_delay: Maximum delay cap (seconds)
        exceptions: Tuple of exceptions to catch and retry
        jitter: Add random jitter
    """
    return retry(
        max_attempts=max_attempts,
        delay=initial_delay,
        backoff=2.0,
        max_delay=max_delay,
        exceptions=exceptions,
        jitter=jitter
    )


def retry_proxy_error(max_attempts: int = 2):
    """
    Retry decorator specifically for proxy errors
    
    Args:
        max_attempts: Maximum retry attempts
    """
    from utils.exceptions import ProxyConnectionError, ProxyValidationError
    
    return retry(
        max_attempts=max_attempts,
        delay=1.0,
        backoff=1.5,
        max_delay=10.0,
        exceptions=(ProxyConnectionError, ProxyValidationError),
        jitter=True
    )


def retry_timeout(max_attempts: int = 2):
    """
    Retry decorator specifically for timeout errors
    
    Args:
        max_attempts: Maximum retry attempts
    """
    from selenium.common.exceptions import TimeoutException
    from utils.exceptions import PageLoadError
    
    return retry(
        max_attempts=max_attempts,
        delay=2.0,
        backoff=2.0,
        max_delay=30.0,
        exceptions=(TimeoutException, PageLoadError),
        jitter=True
    )

