import os
import re
import time
import mysql.connector
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import random
import logging
import requests

# Настройки
OUTPUT_DIR = "/home/admin/web/233204.fornex.cloud/public_html/public/"
OUTPUT_FILENAME = "products.xlsx"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
BASE_URL = "https://trast-zapchast.ru"
THREADS = 2

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Прокси
PROXY_LIST = [
    "vpn-uk1.trafflink.xyz:443", "vpn-uk2.trafflink.xyz:443"
    # ... список обрезан для краткости ...
]

current_proxy = None

def get_random_proxy():
    return random.choice(PROXY_LIST)

def connect_to_db():
    try:
        return mysql.connector.connect(
            host="127.0.0.1",
            user="uploader",
            password="uploader",
            database="avito"
        )
    except mysql.connector.Error as err:
        logging.error(f"Ошибка подключения к базе данных: {err}")
        raise

def update_config_status(db_connection, name, value):
    try:
        with db_connection.cursor() as cursor:
            cursor.execute("REPLACE INTO config (name, value) VALUES (%s, %s)", (name, value))
            db_connection.commit()
            logging.info(f"Статус '{name}' успешно обновлен до '{value}'")
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса '{name}': {e}")
        db_connection.rollback()

def create_driver(proxy=None):
    logging.getLogger('WDM').setLevel(logging.ERROR)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if proxy:
        options.add_argument(f"--proxy-server=https://{proxy}")
    options.add_argument("--log-level=3")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def get_total_pages():
    for proxy in PROXY_LIST:
        try:
            driver = create_driver(proxy)
            driver.get(f"{BASE_URL}/shop/page/1")
            time.sleep(2)
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            pagination = soup.select('ul.page-numbers li')
            driver.quit()
            total_pages = int(pagination[-2].get_text(strip=True)) if pagination else 1
            if total_pages > 1:
                logging.info(f"Найдено страниц: {total_pages} (Прокси: {proxy})")
                return total_pages
        except Exception as e:
            logging.warning(f"Прокси не работает ({proxy}): {e}")
    logging.error("❌ Не удалось найти рабочий прокси для получения количества страниц.")
    return 1

def parse_page(page_number, total_pages):
    driver = create_driver(current_proxy)
    try:
        driver.get(f"{BASE_URL}/shop/page/{page_number}")
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        products = soup.find_all('div', class_='th-product-card')
        items = []
        for product in products:
            if product.find('a', class_='button product_type_variable'):
                continue
            try:
                name = product.find('div', class_='th-product-card__name').find('h2')
                name = name.get_text(strip=True) if name else 'Н/Д'
                price_tag = product.select_one('div.th-product-card__prices span.woocommerce-Price-amount bdi')
                price = re.sub(r'[^\d]', '', price_tag.get_text(strip=True)) if price_tag else '0'
                article = product.find('div', class_='th-product-card__meta').find('span', 'th-product-card__meta-value')
                article = re.sub(r'\s|\-', '', article.get_text(strip=True)) if article else 'Н/Д'
                product_page_tag = product.find('a', class_='woocommerce-LoopProduct-link')
                product_page_link = product_page_tag['href'] if product_page_tag else 'Н/Д'
                manufacturer = get_manufacturer_from_product_page(product_page_link)
                items.append({'Наименование': name, 'Производитель': manufacturer, 'Артикул': article, 'Цена': price})
                logging.info(f"Добавлен товар: {name} | Артикул: {article} | Страница {page_number}/{total_pages}")
            except Exception as e:
                logging.warning(f"Ошибка обработки товара на странице {page_number}: {e}")
                continue
        logging.info(f"Страница {page_number}/{total_pages} обработана. Добавлено товаров: {len(items)}")
        return items
    finally:
        driver.quit()

def get_manufacturer_from_product_page(link):
    try:
        driver = create_driver(current_proxy)
        driver.get(link)
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        manufacturer_tag = soup.select_one('div.wl-attr--item.pa_proizvoditel span.pa-right')
        manufacturer = manufacturer_tag.get_text(strip=True) if manufacturer_tag else "Н/Д"
        driver.quit()
        return manufacturer
    except Exception as e:
        logging.warning(f"⚠️ Не удалось получить производителя для {link}: {e}")
        return "Н/Д"

def check_output_writable():
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_path = os.path.join(OUTPUT_DIR, "test_write_permission.tmp")
        with open(test_path, 'w') as f:
            f.write("test")
        os.remove(test_path)
        return True
    except Exception as e:
        logging.error(f"❌ Невозможно записать файл в директорию {OUTPUT_DIR}: {e}")
        return False

def notify_local_service():
    try:
        response = requests.post("http://localhost:51593", json={}, timeout=10)
        response.raise_for_status()
        logging.info("✅ Ответ от локального сервиса получен успешно")
    except requests.exceptions.Timeout:
        logging.error("⏱ Превышено время ожидания ответа от локального сервиса")
    except requests.exceptions.RequestException as e:
        logging.error(f"🚫 Ошибка при обращении к локальному сервису: {e}")

def main(use_db=False):
    global current_proxy
    current_proxy = None
    if not check_output_writable():
        logging.error("⛔ Парсинг отменён из-за проблем с доступом к файлу.")
        return

    db_connection = None
    try:
        if use_db:
            db_connection = connect_to_db()
            update_config_status(db_connection, "parser_status", "in_progress")

        total_pages = get_total_pages()
        all_items = []
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            futures = [executor.submit(parse_page, page, total_pages) for page in range(1, total_pages + 1)]
            for future in as_completed(futures):
                all_items.extend(future.result())

        df = pd.DataFrame(all_items)
        df.to_excel(OUTPUT_PATH, index=False)
        logging.info(f'✅ Сохранено {len(all_items)} товаров в {OUTPUT_PATH}.')
        notify_local_service()

        if use_db:
            update_config_status(db_connection, "parser_status", "done")
            update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    except Exception as e:
        logging.error(f"Ошибка при обработке: {e}")
        if use_db and db_connection:
            update_config_status(db_connection, "parser_status", "failed")
    finally:
        if db_connection:
            db_connection.close()

if __name__ == '__main__':
    main()
