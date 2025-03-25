import os
import re
import time
import mysql.connector
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import random
import logging

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

# Подключение к базе данных MySQL
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
    attempts = 3  # Количество попыток смены прокси
    for _ in range(attempts):
        proxy = get_random_proxy()
        driver = create_driver(proxy)
        driver.get(f"{BASE_URL}/shop/page/1")
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        pagination = soup.select('ul.page-numbers li')
        driver.quit()
        
        total_pages = int(pagination[-2].get_text(strip=True)) if pagination else 1
        if total_pages > 1:
            current_proxy = proxy
            break
        logging.warning(f'⚠️ Найдена только 1 страница, смена прокси...')
    else:
        logging.error('❌ После нескольких попыток все еще только 1 страница, продолжаем с последним прокси.')
    
    logging.info(f'Используем прокси {current_proxy} для всех страниц.')
    return total_pages

# Функция парсинга страницы каталога
def parse_page(page_number):
    driver = create_driver(current_proxy)
    driver.get(f"{BASE_URL}/shop/page/{page_number}")
    time.sleep(2)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    products = soup.find_all('div', class_='th-product-card')
    
    items = []
    count = 0
    for product in products:
        # Проверка на наличие класса "outofstock" или элемента, который указывает, что товар недоступен
        if product.find('a', class_='button product_type_variable'):
            continue
        
        try:
            name = product.find('div', class_='th-product-card__name').find('h2')
            name = name.get_text(strip=True) if name else 'Н/Д'
            
            price = product.find('div', class_='th-product-card__prices').find('span', class_='woocommerce-Price-amount')
            price = re.sub(r'[^\d]', '', price.get_text(strip=True)) if price else '0'
            
            article = product.find('div', class_='th-product-card__meta').find('span', class_='th-product-card__meta-value')
            article = re.sub(r'[\s\-]', '', article.get_text(strip=True)) if article else 'Н/Д'
            
            image_tag = product.find('div', class_='th-product-card__image').find('img')
            image_url = image_tag['src'] if image_tag else 'Н/Д'
            
            product_page_tag = product.find('a', class_='woocommerce-LoopProduct-link')
            product_page_link = product_page_tag['href'] if product_page_tag else 'Н/Д'
            
            manufacturer = "Н/Д"
            
            items.append({'Наименование': name, 'Производитель': manufacturer, 'Артикул': article, 'Цена': price, 'Изображение': image_url, 'Ссылка': product_page_link})
            count += 1
            logging.info(f'✔️ Добавлен товар: {name} | Артикул: {article} | Цена: {price}')
        except Exception as e:
            logging.warning(f'Ошибка обработки товара на странице {page_number}: {e}')
            continue
    
    driver.quit()
    logging.info(f'📄 Завершена обработка страницы {page_number}. Добавлено товаров: {count}')
    return items

# Основная функция
def main():
    with connect_to_db() as db_connection:
            try:
            # Устанавливаем начальный статус
                update_config_status(db_connection, "parser_status", "in_progress")
                total_pages = get_total_pages()
                logging.info(f'🔍 Найдено страниц: {total_pages}')
                
                all_items = []
                with ThreadPoolExecutor(max_workers=THREADS) as executor:
                    future_to_page = {executor.submit(parse_page, page): page for page in range(1, total_pages + 1)}
                    for future in as_completed(future_to_page):
                        all_items.extend(future.result())
                
                df = pd.DataFrame(all_items)
                df.to_excel(OUTPUT_PATH, index=False)
                logging.info(f'✅ Парсинг завершен, сохранено {len(all_items)} товаров.')
                update_config_status(db_connection, "parser_status", "done")
                update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            


            except Exception as e:
                logging.error(f"Ошибка при обработке: {e}")
                update_config_status(db_connection, "parser_status", "failed")


if __name__ == '__main__':
    main()
