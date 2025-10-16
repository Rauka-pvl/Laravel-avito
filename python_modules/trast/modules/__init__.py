"""
Trast Parser Modules

Modular architecture for reliable web scraping with anti-blocking capabilities.
"""

__version__ = "2.0.0"
__author__ = "AI Assistant"

# Import all main classes for easy access
from .config import TrastConfig
from .proxy_manager import ProxyPool, TorManager, HybridProxyStrategy
from .browser_manager import BrowserFactory, BrowserSession, DisposableBrowserPool
from .anti_block import (
    BlockDetector, 
    HumanBehaviorSimulator, 
    DelayStrategy, 
    SessionEstablisher, 
    FingerprintRandomizer
)
from .parser_core import ProductExtractor, PageFetcher, ParsingOrchestrator
from .data_manager import DataWriter, BackupManager, DataValidator
from .ip_rotator import IPRotationStrategy, RotationTracker, AdaptiveRotator
from .adaptive_learning import AdaptiveLearningEngine, StrategyPerformance, IPPerformance

__all__ = [
    'TrastConfig',
    'ProxyPool', 'TorManager', 'HybridProxyStrategy',
    'BrowserFactory', 'BrowserSession', 'DisposableBrowserPool',
    'BlockDetector', 'HumanBehaviorSimulator', 'DelayStrategy', 
    'SessionEstablisher', 'FingerprintRandomizer',
    'ProductExtractor', 'PageFetcher', 'ParsingOrchestrator',
    'DataWriter', 'BackupManager', 'DataValidator',
    'IPRotationStrategy', 'RotationTracker', 'AdaptiveRotator',
    'AdaptiveLearningEngine', 'StrategyPerformance', 'IPPerformance'
]
