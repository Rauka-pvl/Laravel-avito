import os
import re
import time
import random
import logging
import requests
import shutil
from time import sleep
from datetime import datetime
from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import sys
import csv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from notification.main import TelegramNotifier

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR, BASE_DIR

LOG_DIR = os.path.join(BASE_DIR, "..", "..", "storage", "app", "public", "output", "logs-trast")
OUTPUT_FILE = os.path.join(LOG_DIR, "..", "trast.xlsx")
BACKUP_FILE = os.path.join(LOG_DIR, "..", "trast_backup.xlsx")
CSV_FILE = os.path.join(LOG_DIR, "..", "trast.csv")
BACKUP_CSV = os.path.join(LOG_DIR, "..", "trast_backup.csv")
os.makedirs(LOG_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(LOG_DIR, f"trast_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8-sig"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

total_products = 0

def connect_to_db(retries=3, delay=3):
    for attempt in range(retries):
        try:
            conn = mysql.connector.connect(
                host="127.0.0.1",
                user="uploader",
                password="uploader",
                database="avito"
            )
            if conn.is_connected():
                logger.info("Successfully connected to the database")
                return conn
        except mysql.connector.Error as err:
            logger.warning(f"Attempt {attempt+1}: DB connection error: {err}")
            sleep(delay)
    logger.warning("Database is not available.")
    return None

def update_config_status(db, name, value):
    if not db:
        return
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM config WHERE name = %s", (name,))
            exists = cursor.fetchone()[0]
            if exists:
                cursor.execute("UPDATE config SET value = %s WHERE name = %s", (value, name))
            else:
                cursor.execute("INSERT INTO config (name, value) VALUES (%s, %s)", (name, value))
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating config: {e}")

def create_new_excel(path):
    if os.path.exists(path):
        os.remove(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["Manufacturer", "Article", "Description", "Price"])
    wb.save(path)

def create_new_csv(path):
    if os.path.exists(path):
        os.remove(path)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(["Manufacturer", "Article", "Description", "Price"])

def append_to_excel(path, product_list):
    global total_products
    if not os.path.exists(path):
        create_new_excel(path)
    try:
        wb = load_workbook(path)
        ws = wb.active
        for p in product_list:
            ws.append([
                p.get("manufacturer", ""),
                p.get("article", ""),
                p.get("description", ""),
                p.get("price", {}).get("price", "")
            ])
        wb.save(path)
        total_products += len(product_list)
    except Exception as e:
        logger.error(f"Error writing to Excel: {e}")
    logger.info(f"Excel updated with {len(product_list)} records, file size: {os.path.getsize(OUTPUT_FILE)} bytes")

def append_to_csv(path, product_list):
    try:
        with open(path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            for p in product_list:
                writer.writerow([
                    p.get("manufacturer", ""),
                    p.get("article", ""),
                    p.get("description", ""),
                    p.get("price", {}).get("price", "")
                ])
    except Exception as e:
        logger.error(f"Error writing to CSV: {e}")

def create_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def get_pages_count_with_driver(driver, url="https://trast-zapchast.ru/shop/"):
    driver.get(url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    last_page_el = soup.select_one(".facetwp-pager .facetwp-page.last")
    if last_page_el and last_page_el.has_attr("data-page"):
        return int(last_page_el["data-page"])
    return 1

def get_products_from_page_soup(soup):
    results = []
    cards = soup.select("div.product.product-plate")
    for card in cards:
        stock_badge = card.select_one("div.product-badge.product-stock.instock")
        if not stock_badge or "В наличии" not in stock_badge.text:
            continue

        title_el = card.select_one("a.product-title")
        article_el = card.select_one("div.product-attributes .item:nth-child(1) .value")
        manufacturer_el = card.select_one("div.product-attributes .item:nth-child(2) .value")
        price_el = card.select_one("div.product-price .amount bdi")

        if not (title_el and article_el and manufacturer_el and price_el):
            continue

        title = title_el.text.strip()
        article = article_el.text.strip()
        manufacturer = manufacturer_el.text.strip()
        price = price_el.text.strip().replace("\xa0", " ")

        results.append({
            "manufacturer": manufacturer,
            "article": article,
            "description": title,
            "price": {"price": price}
        })

    return results

def producer():
    thread_name = threading.current_thread().name
    logger.info(f"[{thread_name}] Starting producer thread")
    TelegramNotifier.notify("🚀 Starting Froza parsing")
    driver = create_driver()
    try:
        total_pages = get_pages_count_with_driver(driver)
        # total_pages = 5
        for page_num in range(1, total_pages + 1):
            page_url = f"https://trast-zapchast.ru/shop/?_paged={page_num}/"
            logger.info(f"[{thread_name}] Parsing page {page_num}/{total_pages}")
            driver.get(page_url)
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = get_products_from_page_soup(soup)
            if products:
                append_to_excel(OUTPUT_FILE, products)
                append_to_csv(CSV_FILE, products)
                logger.info(f"[{thread_name}] Page {page_num}: added {len(products)} products")
            else:
                logger.warning(f"[{thread_name}] Page {page_num}: no products found")
            time.sleep(random.uniform(1, 2))
    finally:
        driver.quit()

def create_backup():
    try:
        if os.path.exists(OUTPUT_FILE):
            shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
            logger.info(f"Excel backup created: {BACKUP_FILE}")
        if os.path.exists(CSV_FILE):
            shutil.copy2(CSV_FILE, BACKUP_CSV)
            logger.info(f"CSV backup created: {BACKUP_CSV}")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")

if __name__ == "__main__":
    TelegramNotifier.notify("🚀 Starting Trast script")
    start = time.time()

    create_new_excel(OUTPUT_FILE)
    create_new_csv(CSV_FILE)

    db = connect_to_db()
    if db:
        update_config_status(db, 'parser_status', 'in_progress')
        update_config_status(db, 'parser_update_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    import threading
    t1 = threading.Thread(target=producer, name="Producer")
    t1.start()
    t1.join()

    status = 'done'
    if total_products >= 100:
        logger.info(f"Successfully collected {total_products} items")
        try:
            create_backup()
        except Exception as e:
            logger.error(f"Backup creation error: {e}")
            status = 'error'
    else:
        logger.critical(f"Not enough data collected: {total_products} items")
        status = 'insufficient_data'
        if os.path.exists(BACKUP_FILE):
            shutil.copy2(BACKUP_FILE, OUTPUT_FILE)
            logger.info("Excel restored from backup")
        if os.path.exists(BACKUP_CSV):
            shutil.copy2(BACKUP_CSV, CSV_FILE)
            logger.info("CSV restored from backup")

    if db:
        update_config_status(db, 'parser_status', status)
        update_config_status(db, 'parser_update_time', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        db.close()

    logger.info(f"Completed in {round(time.time() - start, 2)} seconds.")
    TelegramNotifier.notify(f"✅ Trast parsing completed. Total: {total_products} items")