"""
Refactored main module for Trast parser.

Orchestrates all modules with clean integration and adaptive learning.
"""

import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add parent directories to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Import modules
from modules.config import TrastConfig
from modules.proxy_manager import HybridProxyStrategy, Proxy
from modules.browser_manager import BrowserFactory, DisposableBrowserPool, BrowserSession
from modules.anti_block import BlockDetector, HumanBehaviorSimulator, DelayStrategy, SessionEstablisher
from modules.parser_core import ParsingOrchestrator, ProductExtractor
from modules.data_manager import DataWriter, BackupManager, DataValidator
from modules.ip_rotator import AdaptiveRotator
from modules.adaptive_learning import AdaptiveLearningEngine

# Import external dependencies
from bz_telebot.database_manager import set_script_start, set_script_end
from notification.main import TelegramNotifier

# Setup logging
logger = logging.getLogger("trast")

logging.basicConfig(
    level=logging.INFO,
    format=TrastConfig.LOG_FORMAT,
    handlers=[
        logging.FileHandler(
            os.path.join(TrastConfig.LOG_DIR, f"trast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), 
            encoding=TrastConfig.LOG_ENCODING
        ),
        logging.StreamHandler()
    ]
)


class TrastParser:
    """Main parser orchestrator with modular architecture."""
    
    def __init__(self):
        """Initialize all modules."""
        logger.info("=== MODULAR TRAST PARSER v2.0 ===")
        
        # Initialize modules
        self.proxy_strategy = HybridProxyStrategy()
        self.browser_pool = DisposableBrowserPool()
        self.session_establisher = SessionEstablisher()
        self.parser_orchestrator = ParsingOrchestrator()
        self.data_writer = DataWriter()
        self.backup_manager = BackupManager()
        self.data_validator = DataValidator()
        self.ip_rotator = AdaptiveRotator()
        self.learning_engine = AdaptiveLearningEngine()
        
        # Statistics
        self.total_products = 0
        self.session_count = 0
        self.error_count = 0
        self.start_time = None
        
        # Ensure directories exist
        TrastConfig.ensure_directories()
        
        logger.info("✅ All modules initialized successfully")
    
    def run(self) -> int:
        """Main parsing execution."""
        self.start_time = datetime.now()
        logger.info("🚀 Starting modular parsing...")
        
        try:
            # Initialize data files
            self.data_writer.create_excel()
            self.data_writer.create_csv()
            
            # Try bulk fetch first
            bulk_products = self._try_bulk_fetch()
            if bulk_products and len(bulk_products) > 100:
                logger.info(f"✅ Bulk fetch successful! Got {len(bulk_products)} products")
                self._process_products(bulk_products)
                return len(bulk_products)
            
            # Fallback to regular parsing
            logger.info("Bulk fetch failed, using regular parsing...")
            return self._regular_parsing()
            
        except Exception as e:
            logger.error(f"❌ Critical error in main execution: {e}")
            return 0
        finally:
            self._cleanup()
    
    def _try_bulk_fetch(self) -> Optional[List[Dict[str, Any]]]:
        """Try to fetch all data in one request."""
        browser_session = None
        
        try:
            # Get connection
            connection = self.proxy_strategy.get_connection()
            if not connection:
                logger.error("❌ No connection available for bulk fetch")
                return None
            
            # Create browser
            if isinstance(connection, dict):  # Tor connection
                browser_session = self.browser_pool.get_browser(proxy_config=connection)
            else:  # Proxy connection
                browser_session = self.browser_pool.get_browser(proxy=connection)
            
            if not browser_session:
                logger.error("❌ Failed to create browser for bulk fetch")
                return None
            
            # Establish session
            if not self.session_establisher.establish_legitimate_session(browser_session.driver):
                logger.error("❌ Failed to establish session for bulk fetch")
                return None
            
            # Try bulk fetch
            products = ProductExtractor.try_bulk_fetch(browser_session.driver)
            
            if products:
                # Learn from success
                current_ip = self._get_current_ip()
                self.ip_rotator.learn_from_success(current_ip, "bulk_fetch")
                self.learning_engine.learn_from_success("bulk_fetch", current_ip)
                self.proxy_strategy.mark_success()
            
            return products
            
        except Exception as e:
            logger.error(f"❌ Error in bulk fetch: {e}")
            # Learn from failure
            current_ip = self._get_current_ip()
            self.ip_rotator.learn_from_failure(current_ip, "bulk_fetch")
            self.learning_engine.learn_from_failure("bulk_fetch", current_ip, str(e))
            self.proxy_strategy.mark_failure()
            return None
        finally:
            if browser_session:
                browser_session.dispose()
    
    def _regular_parsing(self) -> int:
        """Regular page-by-page parsing."""
        logger.info("📄 Starting regular parsing...")
        
        # Get initial connection
        connection = self.proxy_strategy.get_connection()
        if not connection:
            logger.error("❌ No connection available")
            return 0
        
        # Create initial browser
        browser_session = self._create_browser_session(connection)
        if not browser_session:
            logger.error("❌ Failed to create initial browser")
            return 0
        
        try:
            # Establish session
            if not self.session_establisher.establish_legitimate_session(browser_session.driver):
                logger.error("❌ Failed to establish initial session")
                return 0
            
            # Get total pages
            total_pages = ProductExtractor.get_page_count(browser_session.driver)
            logger.info(f"📊 Total pages to parse: {total_pages}")
            
            # Parse all pages
            all_products = self.parser_orchestrator.parse_all_pages(
                browser_session.driver, 1, total_pages
            )
            
            # Process products
            self._process_products(all_products)
            
            return len(all_products)
            
        except Exception as e:
            logger.error(f"❌ Error in regular parsing: {e}")
            return 0
        finally:
            if browser_session:
                browser_session.dispose()
    
    def _create_browser_session(self, connection) -> Optional[BrowserSession]:
        """Create browser session with connection."""
        try:
            if isinstance(connection, dict):  # Tor connection
                return self.browser_pool.get_browser(proxy_config=connection)
            else:  # Proxy connection
                return self.browser_pool.get_browser(proxy=connection)
        except Exception as e:
            logger.error(f"❌ Error creating browser session: {e}")
            return None
    
    def _process_products(self, products: List[Dict[str, Any]]):
        """Process and save products."""
        if not products:
            logger.warning("⚠️ No products to process")
            return
        
        # Validate products
        valid_products, invalid_products = self.data_validator.validate_product_list(products)
        
        if invalid_products:
            logger.warning(f"⚠️ {len(invalid_products)} invalid products filtered out")
        
        # Save valid products
        if valid_products:
            self.data_writer.append_to_excel(product_list=valid_products)
            self.data_writer.append_to_csv(product_list=valid_products)
            self.total_products = len(valid_products)
            
            logger.info(f"✅ Processed {len(valid_products)} valid products")
        
        # Create backup
        self.backup_manager.create_backup_with_metadata(
            self.data_writer.excel_file,
            self.data_writer.csv_file,
            len(valid_products),
            self.parser_orchestrator.pages_processed
        )
    
    def _get_current_ip(self) -> str:
        """Get current IP address."""
        try:
            if self.proxy_strategy.connection_type == 'tor':
                return self.proxy_strategy.tor_manager.get_current_ip() or "tor_ip"
            else:
                return str(self.proxy_strategy.current_connection) if self.proxy_strategy.current_connection else "proxy_ip"
        except Exception:
            return "unknown_ip"
    
    def _cleanup(self):
        """Cleanup resources."""
        try:
            # Cleanup browser pool
            self.browser_pool.cleanup_all()
            
            # Cleanup old backups
            self.backup_manager.cleanup_old_backups()
            
            logger.info("🧹 Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        return {
            'total_products': self.total_products,
            'session_count': self.session_count,
            'error_count': self.error_count,
            'duration_seconds': duration,
            'proxy_stats': self.proxy_strategy.get_stats(),
            'browser_stats': self.browser_pool.get_stats(),
            'parser_stats': self.parser_orchestrator.get_stats(),
            'data_stats': self.data_writer.get_stats(),
            'backup_stats': self.backup_manager.get_backup_stats(),
            'rotation_stats': self.ip_rotator.get_stats(),
            'learning_stats': self.learning_engine.get_learning_stats()
        }


def main():
    """Main entry point."""
    script_name = "trast_modular"
    
    # Notify start
    TelegramNotifier.notify("🚀 Modular Trast parsing start...")
    set_script_start(script_name)
    
    try:
        # Create and run parser
        parser = TrastParser()
        total_products = parser.run()
        
        # Get final stats
        stats = parser.get_stats()
        
        # Notify completion
        if total_products > 0:
            logger.info("✅ Parsing completed successfully")
            TelegramNotifier.notify(
                f"✅ Modular Trast parsing completed\n"
                f"Products: {total_products}\n"
                f"Duration: {stats['duration_seconds']:.1f}s\n"
                f"Proxy success rate: {stats['proxy_stats'].get('success_rate', 0):.2f}"
            )
            set_script_end(script_name, "completed")
        else:
            logger.error("❌ Parsing failed: 0 products")
            TelegramNotifier.notify("❌ Modular Trast parsing failed: 0 products")
            set_script_end(script_name, "insufficient_data")
            
            # Try smart restore
            if parser.backup_manager.smart_restore(0):
                logger.info("📦 Restored from backup")
                TelegramNotifier.notify("📦 Restored from backup due to failure")
        
        # Log final statistics
        logger.info("📊 Final Statistics:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        
    except Exception as e:
        logger.error(f"❌ Critical error in main: {e}")
        TelegramNotifier.notify(f"❌ Critical error in modular Trast parser: {e}")
        set_script_end(script_name, "error")


if __name__ == "__main__":
    main()
