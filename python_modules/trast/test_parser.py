#!/usr/bin/env python3
"""
Test script for Trast parser.

Tests the basic functionality without requiring external dependencies.
"""

import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported."""
    try:
        from config import TrastConfig
        print("✅ config.py imported successfully")
        
        from logger_setup import setup_logger
        print("✅ logger_setup.py imported successfully")
        
        from connection_manager import ConnectionManager, ConnectionResult
        print("✅ connection_manager.py imported successfully")
        
        from parser import TrastParser
        print("✅ parser.py imported successfully")
        
        from main import TrastMain
        print("✅ main.py imported successfully")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_config():
    """Test configuration values."""
    try:
        from config import TrastConfig
        
        print(f"✅ Base URL: {TrastConfig.BASE_URL}")
        print(f"✅ Shop URL: {TrastConfig.SHOP_URL}")
        print(f"✅ First page URL: {TrastConfig.FIRST_PAGE_URL}")
        print(f"✅ TOR proxy: {TrastConfig.TOR_PROXY_URL}")
        print(f"✅ WARP proxy: {TrastConfig.WARP_PROXY_URL}")
        print(f"✅ Proxy files: {len(TrastConfig.PROXY_FILES)}")
        print(f"✅ User agents: {len(TrastConfig.USER_AGENTS)}")
        
        return True
    except Exception as e:
        print(f"❌ Config test error: {e}")
        return False

def test_logger():
    """Test logger setup."""
    try:
        from logger_setup import setup_logger
        
        logger = setup_logger("test_logger")
        logger.info("Test log message")
        print("✅ Logger setup successful")
        
        return True
    except Exception as e:
        print(f"❌ Logger test error: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Trast Parser Components")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Config Test", test_config),
        ("Logger Test", test_logger),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Parser is ready to use.")
        print("\nTo run the parser:")
        print("  cd python_modules/trast")
        print("  python main.py")
    else:
        print("⚠️ Some tests failed. Check the errors above.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
