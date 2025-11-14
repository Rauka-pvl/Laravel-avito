"""CSV writer for products"""

import csv
import sys
import threading
from pathlib import Path
from typing import List, Dict, Any

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.append(str(Path(__file__).parent.parent))

from logger import get_logger
from config import TEMP_CSV, CSV_FILE

logger = get_logger("storage.csv_writer")

# Thread-safe lock for file operations
_file_lock = threading.Lock()


def create_csv_file(file_path: Path = None):
    """Create a new CSV file with headers"""
    if file_path is None:
        file_path = TEMP_CSV
    
    with _file_lock:
        if file_path.exists():
            file_path.unlink()
        
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Manufacturer", "Article", "Description", "Price"])
        
        logger.debug(f"Created CSV file: {file_path}")


def append_products(products: List[Dict[str, Any]], file_path: Path = None):
    """
    Append products to CSV file (thread-safe)
    
    Args:
        products: List of product dicts with keys: manufacturer, article, description, price
        file_path: Path to CSV file (defaults to TEMP_CSV)
    """
    if not products:
        return
    
    if file_path is None:
        file_path = TEMP_CSV
    
    with _file_lock:
        # Create file if it doesn't exist
        if not file_path.exists():
            create_csv_file(file_path)
        
        try:
            with open(file_path, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                for product in products:
                    price_value = ""
                    if isinstance(product.get("price"), dict):
                        price_value = product["price"].get("price", "")
                    elif product.get("price"):
                        price_value = str(product["price"])
                    
                    writer.writerow([
                        product.get("manufacturer", ""),
                        product.get("article", ""),
                        product.get("description", ""),
                        price_value
                    ])
            
            logger.debug(f"Appended {len(products)} products to CSV")
        except Exception as e:
            logger.error(f"Error writing to CSV: {e}")
            raise


def get_total_products(file_path: Path = None) -> int:
    """Get total number of products in CSV file"""
    if file_path is None:
        file_path = TEMP_CSV
    
    if not file_path.exists():
        return 0
    
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=';')
            # Skip header
            next(reader, None)
            return sum(1 for _ in reader)
    except Exception as e:
        logger.warning(f"Error counting products in CSV: {e}")
        return 0

