"""
Main entry point for Trast parser.

Orchestrates connection testing, page fetching, and page count extraction.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Optional

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TrastConfig
from logger_setup import setup_logger
from connection_manager import ConnectionManager, ConnectionResult
from parser import TrastParser
from proxy_manager import ProxyManager


class TrastMain:
    """Main orchestrator class."""
    
    def __init__(self):
        self.logger = setup_logger("trast_main")
        self.connection_manager = ConnectionManager()
        self.parser = TrastParser()
        self.proxy_manager = ProxyManager()
        self.start_time = datetime.now()
    
    async def run(self) -> bool:
        """Main execution flow."""
        try:
            self.logger.info("=== TRAST PARSER STARTED ===")
            self.logger.info(f"Target URL: {TrastConfig.FIRST_PAGE_URL}")
            self.logger.info(f"Start time: {self.start_time}")
            
            # Step 1: Update proxy list
            self.logger.info("Step 1: Updating proxy list...")
            proxy_count = await self.proxy_manager.update_working_proxies(max_proxies=50)
            self.logger.info(f"📊 Рабочих прокси: {proxy_count}")
            
            # Step 2: Test all connections in parallel
            self.logger.info("Step 2: Testing connections...")
            connection_results = await self.connection_manager.test_all_connections()
            
            # Step 3: Select best connection
            self.logger.info("Step 3: Selecting best connection...")
            best_connection = self.connection_manager.get_best_connection(connection_results)
            
            if not best_connection:
                self.logger.error("No working connections found. Exiting.")
                return False
            
            # Step 4: Parse first page
            self.logger.info("Step 4: Parsing first page...")
            success, page_count, content = self.parser.parse_first_page(best_connection)
            
            if not success:
                self.logger.error("Failed to parse first page. Exiting.")
                return False
            
            # Step 5: Log results
            self.logger.info("Step 5: Logging results...")
            self._log_results(best_connection, page_count, content)
            
            # Step 6: Success summary
            self._log_success_summary(best_connection, page_count)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Critical error in main execution: {e}")
            return False
    
    def _log_results(self, connection: 'ConnectionResult', page_count: Optional[int], content: str):
        """Log detailed results."""
        self.logger.info("=== RESULTS ===")
        self.logger.info(f"Connection type: {connection.connection_type.upper()}")
        self.logger.info(f"IP address: {connection.ip_address}")
        self.logger.info(f"Response time: {connection.response_time:.3f}s")
        
        if page_count:
            self.logger.info(f"Total pages found: {page_count}")
        else:
            self.logger.warning("Page count not found")
        
        # Log content length
        self.logger.info(f"Page content length: {len(content)} characters")
        
        # Log some content preview
        if content:
            preview = content[:200] + "..." if len(content) > 200 else content
            self.logger.debug(f"Content preview: {preview}")
    
    def _log_success_summary(self, connection: 'ConnectionResult', page_count: Optional[int]):
        """Log success summary."""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        self.logger.info("=== SUCCESS SUMMARY ===")
        self.logger.info(f"✅ Parser completed successfully")
        self.logger.info(f"✅ Connection: {connection.connection_type.upper()}")
        self.logger.info(f"✅ IP: {connection.ip_address}")
        self.logger.info(f"✅ Pages: {page_count if page_count else 'Unknown'}")
        self.logger.info(f"✅ Duration: {duration:.2f}s")
        self.logger.info("=== END ===")


async def main():
    """Main entry point."""
    try:
        # Ensure directories exist
        TrastConfig.ensure_directories()
        
        # Create and run parser
        parser_main = TrastMain()
        success = await parser_main.run()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️ Parser interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
