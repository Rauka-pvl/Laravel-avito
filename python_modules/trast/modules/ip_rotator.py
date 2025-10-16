"""
IP rotation controller module for Trast parser.

Handles aggressive IP rotation strategies and adaptive learning.
"""

import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from .config import TrastConfig
from .proxy_manager import HybridProxyStrategy, TorManager, ProxyPool

logger = logging.getLogger("trast.ip_rotator")


@dataclass
class RotationContext:
    """Context for rotation decisions."""
    request_count: int = 0
    error_count: int = 0
    last_rotation: Optional[datetime] = None
    session_duration: float = 0.0
    success_rate: float = 1.0
    current_ip: Optional[str] = None
    rotation_reason: str = ""


class IPRotationStrategy:
    """Base class for IP rotation strategies."""
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Determine if IP should be rotated."""
        raise NotImplementedError
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute IP rotation."""
        raise NotImplementedError
    
    def get_strategy_name(self) -> str:
        """Get strategy name."""
        return self.__class__.__name__


class TimeBasedRotation(IPRotationStrategy):
    """Rotate IP based on time intervals."""
    
    def __init__(self, interval_minutes: int = 5):
        self.interval_minutes = interval_minutes
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Rotate every N minutes."""
        if context.last_rotation is None:
            return True
        
        time_since_rotation = datetime.now() - context.last_rotation
        return time_since_rotation >= timedelta(minutes=self.interval_minutes)
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute time-based rotation."""
        logger.info(f"⏰ Time-based rotation (every {self.interval_minutes} minutes)")
        return proxy_strategy.rotate_ip()
    
    def get_strategy_name(self) -> str:
        return f"TimeBased({self.interval_minutes}m)"


class RequestBasedRotation(IPRotationStrategy):
    """Rotate IP based on request count."""
    
    def __init__(self, max_requests: int = 10):
        self.max_requests = max_requests
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Rotate after N requests."""
        return context.request_count >= self.max_requests
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute request-based rotation."""
        logger.info(f"📊 Request-based rotation (every {self.max_requests} requests)")
        return proxy_strategy.rotate_ip()
    
    def get_strategy_name(self) -> str:
        return f"RequestBased({self.max_requests})"


class ErrorBasedRotation(IPRotationStrategy):
    """Rotate IP based on error count."""
    
    def __init__(self, max_errors: int = 3):
        self.max_errors = max_errors
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Rotate after N errors."""
        return context.error_count >= self.max_errors
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute error-based rotation."""
        logger.info(f"❌ Error-based rotation (after {self.max_errors} errors)")
        return proxy_strategy.rotate_ip()
    
    def get_strategy_name(self) -> str:
        return f"ErrorBased({self.max_errors})"


class SuccessRateBasedRotation(IPRotationStrategy):
    """Rotate IP based on success rate."""
    
    def __init__(self, min_success_rate: float = 0.7):
        self.min_success_rate = min_success_rate
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Rotate if success rate is too low."""
        return context.success_rate < self.min_success_rate
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute success rate-based rotation."""
        logger.info(f"📈 Success rate-based rotation (rate: {context.success_rate:.2f})")
        return proxy_strategy.rotate_ip()
    
    def get_strategy_name(self) -> str:
        return f"SuccessRateBased({self.min_success_rate})"


class AggressiveRotation(IPRotationStrategy):
    """Aggressive rotation - rotate on every request."""
    
    def should_rotate(self, context: RotationContext) -> bool:
        """Always rotate."""
        return True
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> bool:
        """Execute aggressive rotation."""
        logger.info("🚀 Aggressive rotation (every request)")
        return proxy_strategy.rotate_ip()
    
    def get_strategy_name(self) -> str:
        return "Aggressive"


class RotationTracker:
    """Tracks IP usage and rotation effectiveness."""
    
    def __init__(self):
        self.ip_stats: Dict[str, Dict[str, Any]] = {}
        self.rotation_history: List[Dict[str, Any]] = []
        self.strategy_stats: Dict[str, Dict[str, Any]] = {}
    
    def track_ip_usage(self, ip: str, success: bool, strategy: str):
        """Track IP usage statistics."""
        if ip not in self.ip_stats:
            self.ip_stats[ip] = {
                'success_count': 0,
                'failure_count': 0,
                'first_seen': datetime.now(),
                'last_seen': datetime.now(),
                'total_requests': 0,
                'strategies_used': set()
            }
        
        stats = self.ip_stats[ip]
        stats['last_seen'] = datetime.now()
        stats['total_requests'] += 1
        stats['strategies_used'].add(strategy)
        
        if success:
            stats['success_count'] += 1
        else:
            stats['failure_count'] += 1
    
    def track_rotation(self, from_ip: str, to_ip: str, strategy: str, reason: str):
        """Track rotation events."""
        rotation_event = {
            'timestamp': datetime.now(),
            'from_ip': from_ip,
            'to_ip': to_ip,
            'strategy': strategy,
            'reason': reason
        }
        self.rotation_history.append(rotation_event)
        
        # Track strategy statistics
        if strategy not in self.strategy_stats:
            self.strategy_stats[strategy] = {
                'rotation_count': 0,
                'success_count': 0,
                'failure_count': 0
            }
        
        self.strategy_stats[strategy]['rotation_count'] += 1
    
    def is_ip_burned(self, ip: str) -> bool:
        """Check if IP is burned (too many failures)."""
        if ip not in self.ip_stats:
            return False
        
        stats = self.ip_stats[ip]
        total_requests = stats['total_requests']
        failure_rate = stats['failure_count'] / total_requests if total_requests > 0 else 0
        
        # IP is burned if failure rate > 80% and has more than 5 requests
        return failure_rate > 0.8 and total_requests > 5
    
    def get_ip_statistics(self) -> Dict[str, Any]:
        """Get comprehensive IP statistics."""
        total_ips = len(self.ip_stats)
        burned_ips = sum(1 for ip in self.ip_stats if self.is_ip_burned(ip))
        
        return {
            'total_ips': total_ips,
            'burned_ips': burned_ips,
            'active_ips': total_ips - burned_ips,
            'total_rotations': len(self.rotation_history),
            'strategy_stats': self.strategy_stats
        }
    
    def get_best_ips(self, limit: int = 5) -> List[Tuple[str, float]]:
        """Get best performing IPs by success rate."""
        ip_scores = []
        
        for ip, stats in self.ip_stats.items():
            if stats['total_requests'] > 0:
                success_rate = stats['success_count'] / stats['total_requests']
                ip_scores.append((ip, success_rate))
        
        # Sort by success rate (descending)
        ip_scores.sort(key=lambda x: x[1], reverse=True)
        return ip_scores[:limit]


class AdaptiveRotator:
    """Adaptive IP rotator that learns from success/failure patterns."""
    
    def __init__(self):
        self.tracker = RotationTracker()
        self.strategies: List[IPRotationStrategy] = [
            TimeBasedRotation(5),      # Every 5 minutes
            RequestBasedRotation(10),   # Every 10 requests
            ErrorBasedRotation(3),      # After 3 errors
            SuccessRateBasedRotation(0.7),  # If success rate < 70%
            AggressiveRotation()        # Every request
        ]
        self.current_strategy_index = 0
        self.context = RotationContext()
        self.learning_enabled = True
    
    def learn_from_success(self, ip: str, strategy: str):
        """Learn from successful operations."""
        self.tracker.track_ip_usage(ip, True, strategy)
        
        if strategy in self.tracker.strategy_stats:
            self.tracker.strategy_stats[strategy]['success_count'] += 1
        
        # Update context success rate
        self._update_success_rate()
        
        logger.debug(f"✅ Learned from success: IP={ip}, Strategy={strategy}")
    
    def learn_from_failure(self, ip: str, strategy: str):
        """Learn from failed operations."""
        self.tracker.track_ip_usage(ip, False, strategy)
        
        if strategy in self.tracker.strategy_stats:
            self.tracker.strategy_stats[strategy]['failure_count'] += 1
        
        # Update context success rate
        self._update_success_rate()
        
        logger.debug(f"❌ Learned from failure: IP={ip}, Strategy={strategy}")
    
    def _update_success_rate(self):
        """Update context success rate."""
        total_success = sum(stats['success_count'] for stats in self.tracker.strategy_stats.values())
        total_failures = sum(stats['failure_count'] for stats in self.tracker.strategy_stats.values())
        
        if total_success + total_failures > 0:
            self.context.success_rate = total_success / (total_success + total_failures)
    
    def get_best_strategy(self) -> IPRotationStrategy:
        """Get the best performing strategy."""
        if not self.learning_enabled:
            return self.strategies[self.current_strategy_index]
        
        best_strategy = None
        best_score = -1
        
        for strategy in self.strategies:
            strategy_name = strategy.get_strategy_name()
            if strategy_name in self.tracker.strategy_stats:
                stats = self.tracker.strategy_stats[strategy_name]
                total_rotations = stats['rotation_count']
                success_count = stats['success_count']
                
                if total_rotations > 0:
                    success_rate = success_count / total_rotations
                    # Score based on success rate and number of rotations (more data = more reliable)
                    score = success_rate * min(total_rotations / 10, 1.0)
                    
                    if score > best_score:
                        best_score = score
                        best_strategy = strategy
        
        return best_strategy or self.strategies[0]
    
    def should_rotate(self) -> Tuple[bool, str]:
        """Determine if rotation is needed and why."""
        self.context.request_count += 1
        
        # Update context
        self.context.session_duration = time.time()
        
        # Check each strategy
        for strategy in self.strategies:
            if strategy.should_rotate(self.context):
                reason = f"{strategy.get_strategy_name()}: {self._get_rotation_reason(strategy)}"
                return True, reason
        
        return False, ""
    
    def _get_rotation_reason(self, strategy: IPRotationStrategy) -> str:
        """Get human-readable rotation reason."""
        if isinstance(strategy, TimeBasedRotation):
            return f"Time interval ({strategy.interval_minutes}m) exceeded"
        elif isinstance(strategy, RequestBasedRotation):
            return f"Request count ({strategy.max_requests}) exceeded"
        elif isinstance(strategy, ErrorBasedRotation):
            return f"Error count ({strategy.max_errors}) exceeded"
        elif isinstance(strategy, SuccessRateBasedRotation):
            return f"Success rate ({self.context.success_rate:.2f}) below threshold ({strategy.min_success_rate})"
        elif isinstance(strategy, AggressiveRotation):
            return "Aggressive rotation (every request)"
        else:
            return "Unknown reason"
    
    def execute_rotation(self, proxy_strategy: HybridProxyStrategy) -> Tuple[bool, str]:
        """Execute IP rotation."""
        from_ip = proxy_strategy.tor_manager.get_current_ip() if proxy_strategy.connection_type == 'tor' else str(proxy_strategy.current_connection)
        
        # Get best strategy
        strategy = self.get_best_strategy()
        strategy_name = strategy.get_strategy_name()
        
        # Execute rotation
        success = strategy.execute_rotation(proxy_strategy)
        
        # Track rotation
        to_ip = proxy_strategy.tor_manager.get_current_ip() if proxy_strategy.connection_type == 'tor' else str(proxy_strategy.current_connection)
        reason = f"{strategy_name}: {self._get_rotation_reason(strategy)}"
        
        self.tracker.track_rotation(from_ip, to_ip, strategy_name, reason)
        
        # Update context
        self.context.last_rotation = datetime.now()
        self.context.request_count = 0
        self.context.error_count = 0
        
        if success:
            logger.info(f"🔄 IP rotation successful: {from_ip} -> {to_ip}")
        else:
            logger.warning(f"⚠️ IP rotation failed: {from_ip} -> {to_ip}")
        
        return success, reason
    
    def increment_error_count(self):
        """Increment error count in context."""
        self.context.error_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive rotation statistics."""
        ip_stats = self.tracker.get_ip_statistics()
        
        return {
            'context': {
                'request_count': self.context.request_count,
                'error_count': self.context.error_count,
                'success_rate': self.context.success_rate,
                'session_duration': self.context.session_duration
            },
            'ip_statistics': ip_stats,
            'current_strategy': self.get_best_strategy().get_strategy_name(),
            'learning_enabled': self.learning_enabled
        }
