import os
import re
import time
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import mysql.connector
from bs4 import BeautifulSoup
import random
import logging


'''
23
'''
# Настройки
OUTPUT_DIR = "output"
OUTPUT_FILENAME = "products.xlsx"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
BASE_URL = "https://trast-zapchast.ru"
THREADS = 4  # Количество потоков для парсинга каталога

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Прокси-серверы
PROXY_LIST = [
    "vpn-uk1.trafflink.xyz:443",
    "vpn-uk2.trafflink.xyz:443",
    "vpn-uk3.trafflink.xyz:443",
    "uk28.trafcfy.com:437",
    "uk27.trafcfy.com:437",
    "uk36.trafcfy.com:437",
]

current_proxy = None  # Глобальный прокси для многопоточного использования

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

def update_config_status(db_connection, key, value):
    logging.info(f'Обновление статуса в БД: {key} -> {value}')
    """
    Обновляет значение в таблице config.
    Если записи с указанным name нет, она будет создана.
    """
    try:
        with db_connection.cursor() as cursor:
            # Проверяем, существует ли запись
            query_check = "SELECT COUNT(*) FROM config WHERE name = %s"
            cursor.execute(query_check, (name,))
            exists = cursor.fetchone()[0]

            if exists:
                # Обновляем существующую запись
                query_update = "UPDATE config SET value = %s WHERE name = %s"
                cursor.execute(query_update, (value, name))
            else:
                # Создаем новую запись
                query_insert = "INSERT INTO config (name, value) VALUES (%s, %s)"
                cursor.execute(query_insert, (name, value))

            db_connection.commit()
            logging.info(f"Статус '{name}' успешно обновлен до значения '{value}'")
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса '{name}' в таблице config: {e}")
        db_connection.rollback()

# Создаем браузер с выбранным прокси
def create_driver(proxy):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--proxy-server=https://{proxy}")
    options.add_argument("--log-level=3")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    logging.info(f'Используется прокси: {proxy}')
    return driver

# Получаем количество страниц и выбираем прокси
def get_total_pages():
    global current_proxy
    proxy = get_random_proxy()
    driver = create_driver(proxy)
    driver.get(f"{BASE_URL}/shop/page/1")
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    pagination = soup.select('ul.page-numbers li')
    driver.quit()
    
    total_pages = int(pagination[-2].get_text(strip=True)) if pagination else 1
    current_proxy = proxy if total_pages > 1 else get_random_proxy()
    logging.info(f'Используем прокси {current_proxy} для всех страниц.')
    return total_pages

def parse_page(page_number):
    driver = create_driver(current_proxy)
    driver.get(f"{BASE_URL}/shop/page/{page_number}")
    time.sleep(2)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    products = soup.find_all('div', class_='th-product-card')
    
    items = []
    for product in products:
        if product.find('span', class_='out-of-stock'):
            continue
        
        try:
            name = product.find('div', class_='th-product-card__name').find('h2').get_text(strip=True)
            price = re.sub(r'[^\d]', '', product.find('span', class_='woocommerce-Price-amount').get_text(strip=True))
            article = re.sub(r'[\s\-]', '', product.find('span', class_='th-product-card__meta-value').get_text(strip=True))
            image_url = product.find('div', class_='th-product-card__image').find('img')['src']
            product_page_link = product.find('a', class_='woocommerce-LoopProduct-link')['href']
            manufacturer = "Н/Д"
            items.append({'Наименование': name, 'Производитель': manufacturer, 'Артикул': article, 'Цена': price, 'Изображение': image_url, 'Ссылка': product_page_link})
        except Exception as e:
            logging.warning(f'Ошибка обработки товара на странице {page_number}: {e}')
            continue
    
    driver.quit()
    logging.info(f'📄 Завершена обработка страницы {page_number}')
    return items

def main():
    try:
        with connect_to_db() as db_connection:
            update_config_status(db_connection, "parser_status", "in_progress")
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            if os.path.exists(OUTPUT_PATH):
                os.remove(OUTPUT_PATH)
            
            start_time = datetime.now()
            logging.info(f'⏳ Начало парсинга: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')
            total_pages = get_total_pages()
            logging.info(f'🔍 Найдено страниц: {total_pages}')
            
            all_items = []
            with ThreadPoolExecutor(max_workers=THREADS) as executor:
                future_to_page = {executor.submit(parse_page, page): page for page in range(1, total_pages + 1)}
                for future in as_completed(future_to_page):
                    page_number = future_to_page[future]
                    try:
                        items = future.result()
                        all_items.extend(items)
                        logging.info(f'✅ Страница {page_number} обработана.')
                    except Exception as e:
                        logging.warning(f'⚠️ Ошибка при обработке страницы {page_number}: {e}')
            
            df = pd.DataFrame(all_items, columns=['Наименование', 'Производитель', 'Артикул', 'Цена', 'Изображение', 'Ссылка'])
            df.to_excel(OUTPUT_PATH, sheet_name='Товары', index=False)
            
            end_time = datetime.now()
            elapsed_time = end_time - start_time
            logging.info(f'✅ Парсинг завершен! Всего товаров: {len(all_items)}')
            logging.info(f'📂 Данные сохранены в: {OUTPUT_PATH}')
            logging.info(f'⏳ Конец: {end_time.strftime("%Y-%m-%d %H:%M:%S")}')
            logging.info(f'⏱ Время работы: {elapsed_time}')
            update_config_status(db_connection, "parser_status", "done")
            update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logging.error(f"Ошибка при парсинге: {e}")
        update_config_status(db_connection, "parser_status", "failed")
        update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

if __name__ == '__main__':
    main()
