"""Main entry point for Trast Parser V2"""

import sys
import time
import queue
import threading
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger, rename_log_file_by_status
from config import (
    NUM_WORKER_THREADS, EMPTY_PAGES_THRESHOLD, MIN_PRODUCTS_FOR_SUCCESS,
    BUFFER_SIZE, TEMP_CSV, PROXY_COUNTRIES
)
from proxy.manager import ProxyManager
from browser.driver_factory import create_driver
from browser.driver_manager import is_tab_crashed_error, TabCrashedError
from parser.page_parser import parse_page, get_pages_count
from parser.page_validator import get_page_status
from storage.csv_writer import create_csv_file, append_products, get_total_products
from storage.excel_writer import finalize_output_files
from utils.exceptions import PageBlockedError, PageLoadError

# Try to import optional dependencies
try:
    from bz_telebot.database_manager import set_script_start, set_script_end
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger = get_logger()
    logger.warning("Database module not available, continuing without DB")

try:
    from notification.main import TelegramNotifier
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger = get_logger()
    logger.warning("Telegram notifier not available")

logger = get_logger("main")

# Thread-safe locks
file_lock = threading.Lock()


def worker_thread(thread_id: int, page_queue: queue.Queue, proxy_manager: ProxyManager, 
                  total_pages: int = None, proxy_pool: list = None):
    """
    Worker thread for parsing pages
    
    Args:
        thread_id: Thread ID
        page_queue: Queue of page numbers to parse
        proxy_manager: Proxy manager instance
        total_pages: Total pages count (for logging)
        proxy_pool: Pool of working proxies
    """
    thread_name = threading.current_thread().name or f"Worker-{thread_id}"
    logger.info(f"[{thread_name}] Starting worker thread {thread_id}")
    
    local_buffer = []
    pages_parsed = 0
    products_collected = 0
    empty_pages_count = 0
    
    driver = None
    proxy = None
    
    try:
        # Get proxy from pool or manager
        if proxy_pool and len(proxy_pool) > 0:
            if len(proxy_pool) > thread_id:
                proxy = proxy_pool[thread_id]
            else:
                proxy = proxy_pool[0]
            logger.info(f"[{thread_name}] Using proxy from pool: {proxy['ip']}:{proxy['port']}")
        else:
            proxy = proxy_manager.get_proxy_for_thread(thread_id)
            if not proxy:
                logger.error(f"[{thread_name}] Failed to get proxy")
                return
        
        # Create driver
        logger.info(f"[{thread_name}] Creating driver...")
        driver = create_driver(proxy=proxy)
        if not driver:
            logger.error(f"[{thread_name}] Failed to create driver")
            return
        
        logger.info(f"[{thread_name}] Driver created, starting parsing")
        
        # Main parsing loop
        while True:
            try:
                # Get page from queue
                try:
                    page_num = page_queue.get(timeout=1)
                except queue.Empty:
                    logger.info(f"[{thread_name}] Queue empty, finishing (pages: {pages_parsed}, products: {products_collected})")
                    break
                
                logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages if total_pages else '?'}")
                
                try:
                    # Parse page
                    result = parse_page(driver, page_num)
                    
                    if result["status"] == "normal" and result["products"]:
                        # Normal page with products
                        local_buffer.extend(result["products"])
                        products_collected += len(result["products"])
                        empty_pages_count = 0
                        
                        # Write buffer if full
                        if len(local_buffer) >= BUFFER_SIZE:
                            with file_lock:
                                append_products(local_buffer, TEMP_CSV)
                            logger.info(f"[{thread_name}] Page {page_num}: {len(result['products'])} products (buffer: {len(local_buffer)})")
                            local_buffer.clear()
                    
                    elif result["status"] == "empty":
                        # Empty page (end of data)
                        empty_pages_count += 1
                        logger.warning(f"[{thread_name}] Page {page_num}: empty (streak: {empty_pages_count})")
                    
                    elif result["status"] == "blocked":
                        # Blocked - get new proxy
                        logger.warning(f"[{thread_name}] Page {page_num}: blocked, switching proxy")
                        proxy_manager.mark_proxy_failed(proxy)
                        
                        # Get new proxy
                        proxy = proxy_manager.get_proxy_for_thread(thread_id)
                        if proxy:
                            try:
                                driver.quit()
                            except:
                                pass
                            driver = create_driver(proxy=proxy)
                            if driver:
                                logger.info(f"[{thread_name}] New proxy obtained")
                                page_queue.task_done()
                                continue
                    
                    elif result["status"] == "error":
                        logger.error(f"[{thread_name}] Page {page_num}: error - {result.get('reason')}")
                    
                    pages_parsed += 1
                    page_queue.task_done()
                    
                    # Random delay
                    time.sleep(1)
                    
                except TabCrashedError as e:
                    logger.error(f"[{thread_name}] Tab crashed on page {page_num}, recreating driver...")
                    try:
                        driver.quit()
                    except:
                        pass
                    
                    proxy = proxy_manager.get_proxy_for_thread(thread_id)
                    if proxy:
                        driver = create_driver(proxy=proxy)
                        if driver:
                            logger.info(f"[{thread_name}] Driver recreated after tab crash")
                            continue
                    
                    page_queue.task_done()
                    continue
                
                except (PageBlockedError, PageLoadError) as e:
                    logger.warning(f"[{thread_name}] Page {page_num}: {e}, switching proxy")
                    proxy_manager.mark_proxy_failed(proxy)
                    
                    proxy = proxy_manager.get_proxy_for_thread(thread_id)
                    if proxy:
                        try:
                            driver.quit()
                        except:
                            pass
                        driver = create_driver(proxy=proxy)
                        if driver:
                            logger.info(f"[{thread_name}] New proxy after error")
                            page_queue.task_done()
                            continue
                    
                    page_queue.task_done()
                    continue
                
                except Exception as e:
                    error_msg = str(e).lower()
                    logger.error(f"[{thread_name}] Error parsing page {page_num}: {e}")
                    
                    if is_tab_crashed_error(e):
                        logger.error(f"[{thread_name}] Tab crash detected, recreating driver...")
                        try:
                            driver.quit()
                        except:
                            pass
                        
                        proxy = proxy_manager.get_proxy_for_thread(thread_id)
                        if proxy:
                            driver = create_driver(proxy=proxy)
                            if driver:
                                logger.info(f"[{thread_name}] Driver recreated")
                                continue
                    
                    page_queue.task_done()
                    continue
                    
            except Exception as e:
                logger.error(f"[{thread_name}] Critical error in parsing loop: {e}")
                page_queue.task_done()
                continue
        
        # Write remaining buffer
        if local_buffer:
            with file_lock:
                append_products(local_buffer, TEMP_CSV)
            logger.info(f"[{thread_name}] Wrote remaining buffer: {len(local_buffer)} products")
        
        logger.info(f"[{thread_name}] Finished: pages={pages_parsed}, products={products_collected}")
        
    except Exception as e:
        logger.error(f"[{thread_name}] Critical error in worker: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def run_parser(proxy_manager: ProxyManager) -> tuple:
    """
    Main parsing function
    
    Args:
        proxy_manager: Proxy manager instance
    
    Returns:
        Tuple of (total_products, metrics_dict)
    """
    logger.info("=== Starting Trast Parser V2 ===")
    
    # Find working proxies in parallel
    logger.info("Searching for working proxies...")
    found_proxies_list = []
    found_proxies_lock = threading.Lock()
    first_proxy_ready = threading.Event()
    
    def search_proxies_background():
        """Background proxy search"""
        try:
            proxies = proxy_manager.get_working_proxies_parallel(
                count=NUM_WORKER_THREADS,
                callback_list=found_proxies_list,
                callback_event=first_proxy_ready,
                callback_lock=found_proxies_lock
            )
            with found_proxies_lock:
                for proxy in proxies:
                    if proxy not in found_proxies_list:
                        found_proxies_list.append(proxy)
            if proxies:
                logger.info(f"Found {len(proxies)} working proxies")
                first_proxy_ready.set()
        except Exception as e:
            logger.error(f"Error in background proxy search: {e}")
    
    # Start background search
    search_thread = threading.Thread(target=search_proxies_background, daemon=False, name="ProxySearch")
    search_thread.start()
    
    # Wait for first proxy
    logger.info("Waiting for first working proxy...")
    wait_timeout = 600  # 10 minutes
    start_wait = time.time()
    
    while not first_proxy_ready.is_set() and (time.time() - start_wait) < wait_timeout:
        time.sleep(1)
        with found_proxies_lock:
            if len(found_proxies_list) > 0:
                first_proxy_ready.set()
                break
    
    # Get found proxies
    with found_proxies_lock:
        found_proxies = found_proxies_list.copy()
    
    if not found_proxies:
        logger.error("No working proxies found")
        return 0, {"error": "no_proxies"}
    
    logger.info(f"Found {len(found_proxies)} working proxies")
    
    # Get total pages using first proxy
    logger.info("Getting total pages count...")
    proxy = found_proxies[0]
    driver = None
    
    try:
        driver = create_driver(proxy=proxy)
        total_pages = get_pages_count(driver)
        
        if not total_pages or total_pages <= 0:
            logger.warning("Could not determine total pages, using fallback mode")
            total_pages = None
        else:
            logger.info(f"Total pages: {total_pages}")
    except Exception as e:
        logger.error(f"Error getting pages count: {e}")
        total_pages = None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    # Create page queue
    page_queue = queue.Queue()
    if total_pages:
        for page_num in range(1, total_pages + 1):
            page_queue.put(page_num)
    else:
        # Fallback: start with page 1, will continue until empty pages
        page_queue.put(1)
        logger.info("Using fallback mode: will parse until empty pages")
    
    # Start worker threads
    workers = []
    for i in range(NUM_WORKER_THREADS):
        worker = threading.Thread(
            target=worker_thread,
            args=(i, page_queue, proxy_manager, total_pages, found_proxies),
            name=f"Worker-{i}",
            daemon=False
        )
        worker.start()
        workers.append(worker)
        logger.info(f"Started worker thread {i}")
    
    # Wait for all workers
    for worker in workers:
        worker.join()
    
    # Get total products
    total_products = get_total_products(TEMP_CSV)
    
    metrics = {
        "total_products": total_products,
        "total_pages": total_pages
    }
    
    return total_products, metrics


def main():
    """Main entry point"""
    script_name = "trast_v2"
    logger.info("=== TRAST PARSER V2 STARTED ===")
    logger.info(f"Start time: {datetime.now()}")
    
    # Telegram notification
    if TELEGRAM_AVAILABLE:
        try:
            TelegramNotifier.notify("[Trast V2] Update started")
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")
    
    # Database
    if DB_AVAILABLE:
        try:
            set_script_start(script_name)
            logger.info("Database connection successful")
        except Exception as e:
            logger.warning(f"Database connection failed: {e}")
    
    start_time = datetime.now()
    error_message = None
    
    # Create temp CSV file
    try:
        create_csv_file(TEMP_CSV)
        logger.info("Created temp CSV file")
    except Exception as e:
        logger.error(f"Error creating temp CSV: {e}")
        if TELEGRAM_AVAILABLE:
            TelegramNotifier.notify(f"[Trast V2] Update failed — {e}")
        sys.exit(1)
    
    # Initialize proxy manager
    try:
        logger.info("Initializing proxy manager...")
        proxy_manager = ProxyManager(country_filter=PROXY_COUNTRIES)
        logger.info("Proxy manager initialized")
    except Exception as e:
        logger.error(f"Error initializing proxy manager: {e}")
        if TELEGRAM_AVAILABLE:
            TelegramNotifier.notify(f"[Trast V2] Update failed — {e}")
        sys.exit(1)
    
    # Download/update proxies
    try:
        logger.info("Updating proxy list...")
        if proxy_manager.download_proxies(force_update=True):
            logger.info("Proxy list updated")
        else:
            logger.warning("Failed to update proxy list, using cached")
    except Exception as e:
        logger.warning(f"Error updating proxies: {e}, using cached")
    
    # Run parser
    try:
        total_products, metrics = run_parser(proxy_manager)
        logger.info(f"Parser finished: {total_products} products collected")
    except Exception as e:
        logger.error(f"Critical error in parser: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        total_products = 0
        metrics = {"error": str(e)}
        error_message = str(e)
        status = 'error'
        
        if TELEGRAM_AVAILABLE:
            TelegramNotifier.notify(f"[Trast V2] Update failed — {e}")
        
        if DB_AVAILABLE:
            try:
                set_script_end(script_name, status='error')
            except:
                pass
        
        rename_log_file_by_status('error', total_products=0)
        sys.exit(1)
    
    # Determine status
    if total_products == 0:
        status = 'insufficient_data'
    elif total_products >= MIN_PRODUCTS_FOR_SUCCESS:
        status = 'done'
    else:
        status = 'insufficient_data'
    
    # Finalize output files
    try:
        if total_products >= MIN_PRODUCTS_FOR_SUCCESS:
            finalize_output_files()
            logger.info("Output files finalized")
        else:
            logger.warning(f"Insufficient data: {total_products} products (minimum: {MIN_PRODUCTS_FOR_SUCCESS})")
    except Exception as e:
        logger.error(f"Error finalizing files: {e}")
        status = 'error'
        error_message = str(e)
    
    # Database
    if DB_AVAILABLE:
        try:
            set_script_end(script_name, status=status)
        except Exception as e:
            logger.warning(f"Error saving to database: {e}")
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # Log summary
    logger.info("=" * 60)
    logger.info(f"Parsing completed!")
    logger.info(f"Status: {status}")
    logger.info(f"Products collected: {total_products}")
    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info(f"Metrics: {metrics}")
    logger.info("=" * 60)
    
    # Telegram notification
    if TELEGRAM_AVAILABLE:
        try:
            if status == 'done':
                TelegramNotifier.notify(
                    f"[Trast V2] Update completed — Duration: {duration:.2f}s, Products: {total_products}"
                )
            elif status == 'insufficient_data':
                TelegramNotifier.notify(
                    f"[Trast V2] Update completed with insufficient data — Products: {total_products}"
                )
            else:
                TelegramNotifier.notify(
                    f"[Trast V2] Update failed — {error_message or 'Unknown error'}"
                )
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}")
    
    # Rename log file
    rename_log_file_by_status(status, total_products=total_products)
    
    if status != 'done':
        sys.exit(1)


if __name__ == "__main__":
    main()

