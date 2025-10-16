"""
Test script for modular Trast parser.

Validates that all modules can be imported and basic functionality works.
"""

import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    print("🧪 Testing module imports...")
    
    try:
        from modules.config import TrastConfig
        print("✅ Config module imported")
        
        from modules.proxy_manager import ProxyPool, TorManager, HybridProxyStrategy, Proxy
        from modules.warp_manager import WARPManager
        print("✅ Proxy manager module imported")
        
        from modules.browser_manager import BrowserFactory, BrowserSession, DisposableBrowserPool
        print("✅ Browser manager module imported")
        
        from modules.anti_block import BlockDetector, HumanBehaviorSimulator, DelayStrategy, SessionEstablisher
        print("✅ Anti-block module imported")
        
        from modules.parser_core import ProductExtractor, PageFetcher, ParsingOrchestrator
        print("✅ Parser core module imported")
        
        from modules.data_manager import DataWriter, BackupManager, DataValidator
        print("✅ Data manager module imported")
        
        from modules.ip_rotator import IPRotationStrategy, RotationTracker, AdaptiveRotator
        print("✅ IP rotator module imported")
        
        from modules.adaptive_learning import AdaptiveLearningEngine, StrategyPerformance, IPPerformance
        print("✅ Adaptive learning module imported")
        
        print("🎉 All modules imported successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_config():
    """Test configuration module."""
    print("\n🧪 Testing configuration...")
    
    try:
        from modules.config import TrastConfig
        
        # Test basic config
        print(f"✅ Script directory: {TrastConfig.SCRIPT_DIR}")
        print(f"✅ Proxy files: {TrastConfig.PROXY_FILES}")
        print(f"✅ User agents: {len(TrastConfig.USER_AGENTS)}")
        
        # Test methods
        user_agent = TrastConfig.get_random_user_agent()
        print(f"✅ Random user agent: {user_agent[:50]}...")
        
        viewport = TrastConfig.get_random_viewport()
        print(f"✅ Random viewport: {viewport}")
        
        proxy_paths = TrastConfig.get_proxy_file_paths()
        print(f"✅ Proxy file paths: {len(proxy_paths)} files")
        
        return True
        
    except Exception as e:
        print(f"❌ Config test error: {e}")
        return False

def test_proxy_manager():
    """Test proxy manager module."""
    print("\n🧪 Testing proxy manager...")
    
    try:
        from modules.proxy_manager import ProxyPool, TorManager, HybridProxyStrategy, Proxy
        from modules.warp_manager import WARPManager
        
        # Test proxy pool
        proxy_pool = ProxyPool()
        stats = proxy_pool.get_stats()
        print(f"✅ Proxy pool stats: {stats}")
        
        # Test Tor manager
        tor_manager = TorManager()
        tor_available = tor_manager.is_available()
        print(f"✅ Tor available: {tor_available}")
        
        # Test WARP manager
        warp_manager = WARPManager()
        warp_stats = warp_manager.get_stats()
        print(f"✅ WARP manager stats: {warp_stats}")
        
        # Test hybrid strategy
        hybrid_strategy = HybridProxyStrategy()
        hybrid_stats = hybrid_strategy.get_stats()
        print(f"✅ Hybrid strategy stats: {hybrid_stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Proxy manager test error: {e}")
        return False

def test_adaptive_learning():
    """Test adaptive learning module."""
    print("\n🧪 Testing adaptive learning...")
    
    try:
        from modules.adaptive_learning import AdaptiveLearningEngine, StrategyPerformance, IPPerformance
        
        # Test learning engine
        learning_engine = AdaptiveLearningEngine()
        
        # Test learning from success
        learning_engine.learn_from_success("test_strategy", "192.168.1.1", 1.5)
        learning_engine.learn_from_failure("test_strategy", "192.168.1.2", "timeout")
        
        # Test recommendations
        recommendations = learning_engine.get_strategy_recommendations()
        print(f"✅ Learning recommendations: {recommendations['learning_summary']}")
        
        # Test stats
        stats = learning_engine.get_learning_stats()
        print(f"✅ Learning stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Adaptive learning test error: {e}")
        return False

def test_data_manager():
    """Test data manager module."""
    print("\n🧪 Testing data manager...")
    
    try:
        from modules.data_manager import DataWriter, BackupManager, DataValidator
        
        # Test data writer
        data_writer = DataWriter()
        writer_stats = data_writer.get_stats()
        print(f"✅ Data writer stats: {writer_stats}")
        
        # Test backup manager
        backup_manager = BackupManager()
        backup_stats = backup_manager.get_backup_stats()
        print(f"✅ Backup manager stats: {backup_stats}")
        
        # Test data validator
        test_products = [
            {
                "manufacturer": "Test",
                "article": "12345",
                "description": "Test product",
                "price": {"price": "1000"}
            },
            {
                "manufacturer": "",  # Invalid - empty
                "article": "67890",
                "description": "Invalid product",
                "price": {"price": "2000"}
            }
        ]
        
        valid_products, invalid_products = DataValidator.validate_product_list(test_products)
        print(f"✅ Data validation: {len(valid_products)} valid, {len(invalid_products)} invalid")
        
        return True
        
    except Exception as e:
        print(f"❌ Data manager test error: {e}")
        return False

def test_firefox_browser():
    """Test Firefox browser creation and proxy integration."""
    print("🧪 Testing Firefox browser manager...")
    
    try:
        from modules.browser_manager import BrowserFactory, DisposableBrowserPool
        
        # Test Firefox browser creation
        print("  🔥 Testing Firefox browser creation...")
        driver = BrowserFactory.create_stealth_browser(headless=True)
        
        if driver:
            print("  ✅ Firefox browser created successfully")
            
            # Test basic functionality
            driver.get("https://httpbin.org/ip")
            title = driver.title
            print(f"  ✅ Firefox navigation test passed: {title}")
            
            driver.quit()
            print("  ✅ Firefox browser disposed successfully")
        else:
            print("  ❌ Firefox browser creation failed")
            return False
        
        # Test browser pool
        print("  🏊 Testing Firefox browser pool...")
        pool = DisposableBrowserPool(max_sessions=2)
        
        session1 = pool.get_browser()
        if session1:
            print("  ✅ Firefox session 1 created")
            session1.dispose()
        
        session2 = pool.get_browser()
        if session2:
            print("  ✅ Firefox session 2 created")
            session2.dispose()
        
        pool.cleanup_all()
        print("  ✅ Firefox browser pool test passed")
        
        return True
        
    except Exception as e:
        print(f"❌ Firefox browser test error: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting modular Trast parser tests...\n")
    
    tests = [
        test_imports,
        test_config,
        test_proxy_manager,
        test_adaptive_learning,
        test_data_manager,
        test_firefox_browser
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Modular parser is ready.")
        return True
    else:
        print("❌ Some tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
