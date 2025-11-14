"""Circuit Breaker pattern implementation for proxies and drivers"""

import time
import threading
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS
)

logger = get_logger("utils.circuit_breaker")


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


class CircuitBreaker:
    """
    Circuit breaker implementation for preventing cascading failures
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing recovery, allow limited requests
    """
    
    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
        half_open_max_calls: int = CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
        name: str = "CircuitBreaker"
    ):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            half_open_max_calls: Max calls allowed in half-open state
            name: Name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.name = name
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
        self.lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            Exception: If circuit is open or function fails
        """
        with self.lock:
            # Check if circuit should transition
            self._check_state_transition()
            
            # Reject if circuit is open
            if self.state == CircuitState.OPEN:
                from utils.exceptions import ProxyCircuitBreakerOpen
                raise ProxyCircuitBreakerOpen(
                    f"Circuit breaker {self.name} is OPEN. "
                    f"Last failure: {self.last_failure_time}"
                )
            
            # Limit calls in half-open state
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    from utils.exceptions import ProxyCircuitBreakerOpen
                    raise ProxyCircuitBreakerOpen(
                        f"Circuit breaker {self.name} is HALF_OPEN. "
                        f"Max calls ({self.half_open_max_calls}) reached."
                    )
                self.half_open_calls += 1
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _check_state_transition(self):
        """Check and update circuit breaker state"""
        now = datetime.now()
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time and \
               (now - self.last_failure_time).total_seconds() >= self.recovery_timeout:
                logger.info(f"Circuit breaker {self.name} transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
        
        elif self.state == CircuitState.HALF_OPEN:
            # Check if we have enough successes to close
            if self.success_count >= self.half_open_max_calls:
                logger.info(f"Circuit breaker {self.name} transitioning to CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
    
    def _on_success(self):
        """Handle successful call"""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            
            if self.state == CircuitState.HALF_OPEN:
                # Failure in half-open, go back to open
                logger.warning(
                    f"Circuit breaker {self.name} failure in HALF_OPEN, "
                    f"transitioning to OPEN"
                )
                self.state = CircuitState.OPEN
                self.half_open_calls = 0
                self.success_count = 0
            
            elif self.state == CircuitState.CLOSED:
                # Check if threshold reached
                if self.failure_count >= self.failure_threshold:
                    logger.warning(
                        f"Circuit breaker {self.name} failure threshold reached "
                        f"({self.failure_count}/{self.failure_threshold}), "
                        f"transitioning to OPEN"
                    )
                    self.state = CircuitState.OPEN
    
    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        with self.lock:
            logger.info(f"Circuit breaker {self.name} manually reset")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.half_open_calls = 0
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state"""
        with self.lock:
            return self.state
    
    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        with self.lock:
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
                "half_open_calls": self.half_open_calls
            }

