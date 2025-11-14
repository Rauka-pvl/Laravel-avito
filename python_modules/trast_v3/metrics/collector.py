"""Metrics collector for tracking parser performance"""

import time
import threading
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import METRICS_ENABLED, METRICS_LOG_INTERVAL

logger = get_logger("metrics.collector")


class MetricsCollector:
    """
    Thread-safe metrics collector for parser statistics
    """
    
    def __init__(self):
        self.enabled = METRICS_ENABLED
        self.lock = threading.Lock()
        
        # Counters
        self.pages_parsed = 0
        self.pages_failed = 0
        self.pages_blocked = 0
        self.pages_empty = 0
        self.pages_partial = 0
        self.products_collected = 0
        
        # Proxy metrics
        self.proxy_switches = 0
        self.proxy_failures = 0
        self.proxy_successes = 0
        
        # Driver metrics
        self.driver_creations = 0
        self.driver_crashes = 0
        self.driver_recreations = 0
        
        # Error tracking
        self.errors_by_type: Dict[str, int] = defaultdict(int)
        
        # Timing metrics
        self.page_load_times: deque = deque(maxlen=100)  # Last 100 page loads
        self.proxy_response_times: deque = deque(maxlen=100)
        
        # Start time
        self.start_time = datetime.now()
        self.last_log_time = datetime.now()
    
    def record_page_parsed(self, success: bool = True):
        """Record page parsing attempt"""
        if not self.enabled:
            return
        
        with self.lock:
            if success:
                self.pages_parsed += 1
            else:
                self.pages_failed += 1
    
    def record_page_status(self, status: str):
        """Record page status"""
        if not self.enabled:
            return
        
        with self.lock:
            if status == "blocked":
                self.pages_blocked += 1
            elif status == "empty":
                self.pages_empty += 1
            elif status == "partial":
                self.pages_partial += 1
    
    def record_products(self, count: int):
        """Record products collected"""
        if not self.enabled:
            return
        
        with self.lock:
            self.products_collected += count
    
    def record_proxy_switch(self):
        """Record proxy switch"""
        if not self.enabled:
            return
        
        with self.lock:
            self.proxy_switches += 1
    
    def record_proxy_failure(self):
        """Record proxy failure"""
        if not self.enabled:
            return
        
        with self.lock:
            self.proxy_failures += 1
    
    def record_proxy_success(self):
        """Record proxy success"""
        if not self.enabled:
            return
        
        with self.lock:
            self.proxy_successes += 1
    
    def record_driver_creation(self):
        """Record driver creation"""
        if not self.enabled:
            return
        
        with self.lock:
            self.driver_creations += 1
    
    def record_driver_crash(self):
        """Record driver crash"""
        if not self.enabled:
            return
        
        with self.lock:
            self.driver_crashes += 1
    
    def record_driver_recreation(self):
        """Record driver recreation"""
        if not self.enabled:
            return
        
        with self.lock:
            self.driver_recreations += 1
    
    def record_error(self, error_type: str):
        """Record error by type"""
        if not self.enabled:
            return
        
        with self.lock:
            self.errors_by_type[error_type] += 1
    
    def record_page_load_time(self, load_time: float):
        """Record page load time"""
        if not self.enabled:
            return
        
        with self.lock:
            self.page_load_times.append(load_time)
    
    def record_proxy_response_time(self, response_time: float):
        """Record proxy response time"""
        if not self.enabled:
            return
        
        with self.lock:
            self.proxy_response_times.append(response_time)
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        with self.lock:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            
            # Calculate averages
            avg_page_load_time = (
                sum(self.page_load_times) / len(self.page_load_times)
                if self.page_load_times else 0
            )
            avg_proxy_response_time = (
                sum(self.proxy_response_times) / len(self.proxy_response_times)
                if self.proxy_response_times else 0
            )
            
            # Calculate rates
            pages_per_second = self.pages_parsed / elapsed if elapsed > 0 else 0
            products_per_second = self.products_collected / elapsed if elapsed > 0 else 0
            
            return {
                "elapsed_seconds": elapsed,
                "pages": {
                    "parsed": self.pages_parsed,
                    "failed": self.pages_failed,
                    "blocked": self.pages_blocked,
                    "empty": self.pages_empty,
                    "partial": self.pages_partial,
                    "total": self.pages_parsed + self.pages_failed,
                    "success_rate": (
                        self.pages_parsed / (self.pages_parsed + self.pages_failed)
                        if (self.pages_parsed + self.pages_failed) > 0 else 0
                    ),
                    "pages_per_second": pages_per_second
                },
                "products": {
                    "collected": self.products_collected,
                    "products_per_second": products_per_second
                },
                "proxy": {
                    "switches": self.proxy_switches,
                    "failures": self.proxy_failures,
                    "successes": self.proxy_successes,
                    "success_rate": (
                        self.proxy_successes / (self.proxy_successes + self.proxy_failures)
                        if (self.proxy_successes + self.proxy_failures) > 0 else 0
                    )
                },
                "driver": {
                    "creations": self.driver_creations,
                    "crashes": self.driver_crashes,
                    "recreations": self.driver_recreations,
                    "crash_rate": (
                        self.driver_crashes / self.driver_creations
                        if self.driver_creations > 0 else 0
                    )
                },
                "timing": {
                    "avg_page_load_time": avg_page_load_time,
                    "avg_proxy_response_time": avg_proxy_response_time,
                    "min_page_load_time": min(self.page_load_times) if self.page_load_times else 0,
                    "max_page_load_time": max(self.page_load_times) if self.page_load_times else 0
                },
                "errors": dict(self.errors_by_type)
            }
    
    def log_stats(self, force: bool = False):
        """Log current statistics"""
        if not self.enabled:
            return
        
        now = datetime.now()
        elapsed_since_last_log = (now - self.last_log_time).total_seconds()
        
        if not force and elapsed_since_last_log < METRICS_LOG_INTERVAL:
            return
        
        stats = self.get_stats()
        
        logger.info("=" * 60)
        logger.info("METRICS SUMMARY")
        logger.info(f"Elapsed: {stats['elapsed_seconds']:.1f}s")
        logger.info(f"Pages: {stats['pages']['parsed']} parsed, "
                   f"{stats['pages']['failed']} failed "
                   f"(success rate: {stats['pages']['success_rate']*100:.1f}%)")
        logger.info(f"Products: {stats['products']['collected']} collected "
                   f"({stats['products']['products_per_second']:.2f}/s)")
        logger.info(f"Proxy: {stats['proxy']['switches']} switches, "
                   f"{stats['proxy']['successes']} successes, "
                   f"{stats['proxy']['failures']} failures")
        logger.info(f"Driver: {stats['driver']['creations']} creations, "
                   f"{stats['driver']['crashes']} crashes")
        if stats['timing']['avg_page_load_time'] > 0:
            logger.info(f"Timing: avg page load {stats['timing']['avg_page_load_time']:.2f}s")
        if stats['errors']:
            logger.info(f"Errors: {stats['errors']}")
        logger.info("=" * 60)
        
        with self.lock:
            self.last_log_time = now
    
    def reset(self):
        """Reset all metrics"""
        with self.lock:
            self.pages_parsed = 0
            self.pages_failed = 0
            self.pages_blocked = 0
            self.pages_empty = 0
            self.pages_partial = 0
            self.products_collected = 0
            self.proxy_switches = 0
            self.proxy_failures = 0
            self.proxy_successes = 0
            self.driver_creations = 0
            self.driver_crashes = 0
            self.driver_recreations = 0
            self.errors_by_type.clear()
            self.page_load_times.clear()
            self.proxy_response_times.clear()
            self.start_time = datetime.now()
            self.last_log_time = datetime.now()


# Global metrics collector instance
metrics = MetricsCollector()

