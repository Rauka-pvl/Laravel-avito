"""
Adaptive learning module for Trast parser.

Tracks and learns from successful strategies to optimize performance.
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from .config import TrastConfig

logger = logging.getLogger("trast.adaptive_learning")


@dataclass
class StrategyPerformance:
    """Tracks performance of a specific strategy."""
    strategy_name: str
    success_count: int = 0
    failure_count: int = 0
    total_requests: int = 0
    avg_response_time: float = 0.0
    last_used: Optional[datetime] = None
    first_used: Optional[datetime] = None
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests
    
    @property
    def reliability_score(self) -> float:
        """Calculate reliability score based on multiple factors."""
        if self.total_requests == 0:
            return 0.0
        
        # Base success rate
        base_score = self.success_rate
        
        # Bonus for consistency (low variance in consecutive successes/failures)
        consistency_bonus = min(self.consecutive_successes / 10, 0.2)
        
        # Penalty for recent failures
        failure_penalty = min(self.consecutive_failures * 0.1, 0.3)
        
        # Recency bonus (more recent usage = higher score)
        recency_bonus = 0.0
        if self.last_used:
            hours_since_last_use = (datetime.now() - self.last_used).total_seconds() / 3600
            if hours_since_last_use < 24:  # Used within last 24 hours
                recency_bonus = 0.1
        
        final_score = base_score + consistency_bonus - failure_penalty + recency_bonus
        return max(0.0, min(1.0, final_score))


@dataclass
class IPPerformance:
    """Tracks performance of a specific IP address."""
    ip_address: str
    success_count: int = 0
    failure_count: int = 0
    total_requests: int = 0
    avg_response_time: float = 0.0
    last_used: Optional[datetime] = None
    first_seen: Optional[datetime] = None
    is_burned: bool = False
    burn_reason: str = ""
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests
    
    @property
    def is_reliable(self) -> bool:
        """Check if IP is reliable."""
        return (self.success_rate > 0.7 and 
                self.total_requests > 5 and 
                not self.is_burned)


class AdaptiveLearningEngine:
    """Main adaptive learning engine."""
    
    def __init__(self, learning_file: str = None):
        self.learning_file = learning_file or os.path.join(TrastConfig.SCRIPT_DIR, "learning_data.json")
        self.strategy_performance: Dict[str, StrategyPerformance] = {}
        self.ip_performance: Dict[str, IPPerformance] = {}
        self.learning_enabled = True
        self.min_samples_for_learning = 5
        
        # Load existing learning data
        self._load_learning_data()
    
    def _load_learning_data(self):
        """Load learning data from file."""
        try:
            if os.path.exists(self.learning_file):
                with open(self.learning_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load strategy performance
                for strategy_name, perf_data in data.get('strategies', {}).items():
                    perf_data['first_used'] = datetime.fromisoformat(perf_data['first_used']) if perf_data.get('first_used') else None
                    perf_data['last_used'] = datetime.fromisoformat(perf_data['last_used']) if perf_data.get('last_used') else None
                    self.strategy_performance[strategy_name] = StrategyPerformance(**perf_data)
                
                # Load IP performance
                for ip_address, perf_data in data.get('ips', {}).items():
                    perf_data['first_seen'] = datetime.fromisoformat(perf_data['first_seen']) if perf_data.get('first_seen') else None
                    perf_data['last_used'] = datetime.fromisoformat(perf_data['last_used']) if perf_data.get('last_used') else None
                    self.ip_performance[ip_address] = IPPerformance(**perf_data)
                
                logger.info(f"📚 Loaded learning data: {len(self.strategy_performance)} strategies, {len(self.ip_performance)} IPs")
        except Exception as e:
            logger.error(f"Error loading learning data: {e}")
    
    def _save_learning_data(self):
        """Save learning data to file."""
        try:
            data = {
                'strategies': {},
                'ips': {},
                'last_updated': datetime.now().isoformat()
            }
            
            # Convert strategy performance to serializable format
            for strategy_name, perf in self.strategy_performance.items():
                perf_dict = asdict(perf)
                perf_dict['first_used'] = perf.first_used.isoformat() if perf.first_used else None
                perf_dict['last_used'] = perf.last_used.isoformat() if perf.last_used else None
                data['strategies'][strategy_name] = perf_dict
            
            # Convert IP performance to serializable format
            for ip_address, perf in self.ip_performance.items():
                perf_dict = asdict(perf)
                perf_dict['first_seen'] = perf.first_seen.isoformat() if perf.first_seen else None
                perf_dict['last_used'] = perf.last_used.isoformat() if perf.last_used else None
                data['ips'][ip_address] = perf_dict
            
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Error saving learning data: {e}")
    
    def learn_from_success(self, strategy_name: str, ip_address: str, response_time: float = 0.0):
        """Learn from successful operation."""
        if not self.learning_enabled:
            return
        
        # Update strategy performance
        if strategy_name not in self.strategy_performance:
            self.strategy_performance[strategy_name] = StrategyPerformance(
                strategy_name=strategy_name,
                first_used=datetime.now()
            )
        
        perf = self.strategy_performance[strategy_name]
        perf.success_count += 1
        perf.total_requests += 1
        perf.consecutive_successes += 1
        perf.consecutive_failures = 0
        perf.last_used = datetime.now()
        
        # Update average response time
        if response_time > 0:
            perf.avg_response_time = (perf.avg_response_time * (perf.total_requests - 1) + response_time) / perf.total_requests
        
        # Update IP performance
        if ip_address not in self.ip_performance:
            self.ip_performance[ip_address] = IPPerformance(
                ip_address=ip_address,
                first_seen=datetime.now()
            )
        
        ip_perf = self.ip_performance[ip_address]
        ip_perf.success_count += 1
        ip_perf.total_requests += 1
        ip_perf.last_used = datetime.now()
        
        if response_time > 0:
            ip_perf.avg_response_time = (ip_perf.avg_response_time * (ip_perf.total_requests - 1) + response_time) / ip_perf.total_requests
        
        logger.debug(f"✅ Learned from success: {strategy_name} + {ip_address}")
    
    def learn_from_failure(self, strategy_name: str, ip_address: str, failure_reason: str = ""):
        """Learn from failed operation."""
        if not self.learning_enabled:
            return
        
        # Update strategy performance
        if strategy_name not in self.strategy_performance:
            self.strategy_performance[strategy_name] = StrategyPerformance(
                strategy_name=strategy_name,
                first_used=datetime.now()
            )
        
        perf = self.strategy_performance[strategy_name]
        perf.failure_count += 1
        perf.total_requests += 1
        perf.consecutive_failures += 1
        perf.consecutive_successes = 0
        perf.last_used = datetime.now()
        
        # Update IP performance
        if ip_address not in self.ip_performance:
            self.ip_performance[ip_address] = IPPerformance(
                ip_address=ip_address,
                first_seen=datetime.now()
            )
        
        ip_perf = self.ip_performance[ip_address]
        ip_perf.failure_count += 1
        ip_perf.total_requests += 1
        ip_perf.last_used = datetime.now()
        
        # Mark IP as burned if failure rate is too high
        if ip_perf.total_requests > 5 and ip_perf.success_rate < 0.2:
            ip_perf.is_burned = True
            ip_perf.burn_reason = f"Low success rate: {ip_perf.success_rate:.2f}"
            logger.warning(f"🔥 IP {ip_address} marked as burned: {ip_perf.burn_reason}")
        
        logger.debug(f"❌ Learned from failure: {strategy_name} + {ip_address} ({failure_reason})")
    
    def get_best_strategy(self) -> Optional[str]:
        """Get the best performing strategy."""
        if not self.strategy_performance:
            return None
        
        # Filter strategies with enough samples
        valid_strategies = {
            name: perf for name, perf in self.strategy_performance.items()
            if perf.total_requests >= self.min_samples_for_learning
        }
        
        if not valid_strategies:
            return None
        
        # Find strategy with highest reliability score
        best_strategy = max(valid_strategies.items(), key=lambda x: x[1].reliability_score)
        return best_strategy[0]
    
    def get_best_ips(self, limit: int = 5) -> List[Tuple[str, float]]:
        """Get best performing IPs."""
        # Filter reliable IPs
        reliable_ips = {
            ip: perf for ip, perf in self.ip_performance.items()
            if perf.is_reliable and perf.total_requests >= self.min_samples_for_learning
        }
        
        if not reliable_ips:
            return []
        
        # Sort by success rate
        sorted_ips = sorted(reliable_ips.items(), key=lambda x: x[1].success_rate, reverse=True)
        return [(ip, perf.success_rate) for ip, perf in sorted_ips[:limit]]
    
    def get_strategy_recommendations(self) -> Dict[str, Any]:
        """Get strategy recommendations based on learning."""
        recommendations = {
            'best_strategy': self.get_best_strategy(),
            'best_ips': self.get_best_ips(),
            'strategy_rankings': [],
            'ip_rankings': [],
            'learning_summary': {}
        }
        
        # Strategy rankings
        strategy_scores = [
            (name, perf.reliability_score, perf.success_rate, perf.total_requests)
            for name, perf in self.strategy_performance.items()
            if perf.total_requests >= self.min_samples_for_learning
        ]
        strategy_scores.sort(key=lambda x: x[1], reverse=True)
        recommendations['strategy_rankings'] = strategy_scores
        
        # IP rankings
        ip_scores = [
            (ip, perf.success_rate, perf.total_requests, perf.is_burned)
            for ip, perf in self.ip_performance.items()
            if perf.total_requests >= self.min_samples_for_learning
        ]
        ip_scores.sort(key=lambda x: x[1], reverse=True)
        recommendations['ip_rankings'] = ip_scores
        
        # Learning summary
        recommendations['learning_summary'] = {
            'total_strategies': len(self.strategy_performance),
            'total_ips': len(self.ip_performance),
            'burned_ips': sum(1 for perf in self.ip_performance.values() if perf.is_burned),
            'learning_enabled': self.learning_enabled
        }
        
        return recommendations
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old learning data."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        # Remove old strategies
        strategies_to_remove = [
            name for name, perf in self.strategy_performance.items()
            if perf.last_used and perf.last_used < cutoff_date and perf.total_requests < 10
        ]
        
        for strategy_name in strategies_to_remove:
            del self.strategy_performance[strategy_name]
        
        # Remove old IPs
        ips_to_remove = [
            ip for ip, perf in self.ip_performance.items()
            if perf.last_used and perf.last_used < cutoff_date and perf.total_requests < 10
        ]
        
        for ip_address in ips_to_remove:
            del self.ip_performance[ip_address]
        
        if strategies_to_remove or ips_to_remove:
            logger.info(f"🧹 Cleaned up {len(strategies_to_remove)} old strategies and {len(ips_to_remove)} old IPs")
            self._save_learning_data()
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get comprehensive learning statistics."""
        return {
            'learning_enabled': self.learning_enabled,
            'strategy_count': len(self.strategy_performance),
            'ip_count': len(self.ip_performance),
            'burned_ip_count': sum(1 for perf in self.ip_performance.values() if perf.is_burned),
            'best_strategy': self.get_best_strategy(),
            'best_ips': self.get_best_ips(),
            'learning_file': self.learning_file
        }
    
    def __del__(self):
        """Save learning data on destruction."""
        try:
            self._save_learning_data()
        except Exception:
            pass  # Ignore errors during cleanup
