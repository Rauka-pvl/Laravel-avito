import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os
from datetime import datetime
import logging
import mysql.connector
from concurrent.futures import ThreadPoolExecutor, as_completed

# Настройки
OUTPUT_DIR = "/home/admin/web/233204.fornex.cloud/public_html/public/"
LOG_DIR = "/home/admin/web/233204.fornex.cloud/public_html/storage/logs/update/"
OUTPUT_FILENAME = "products.xlsx"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)
LOG_FILE = os.path.join(LOG_DIR, "parsing_log.txt")  # Путь к файлу для логов

# Настройка логгера для дублирования вывода
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Формат логов
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Консольный обработчик (вывод в консоль)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Файл для логирования
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Функция для получения количества страниц
def get_total_pages():
    url = 'https://trast-zapchast.ru/shop/page/1'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f'❌ Ошибка {response.status_code} при загрузке страницы 1')
        return 1  

    soup = BeautifulSoup(response.text, 'html.parser')
    pagination = soup.select('ul.page-numbers li')  
    if pagination:
        last_page = pagination[-2].get_text(strip=True)  
        return int(last_page) if last_page.isdigit() else 1
    return 1

# Функция очистки данных
def clean_price(price):
    return re.sub(r'[^\d]', '', price)

def clean_article(article):
    return re.sub(r'[\s\-]', '', article)

# Функция для парсинга страницы товара и получения производителя
def parse_product_page(product_url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    response = requests.get(product_url, headers=headers)
    if response.status_code != 200:
        logger.warning(f'⚠️ Ошибка {response.status_code} при загрузке страницы товара: {product_url}')
        return 'Н/Д'

    soup = BeautifulSoup(response.text, 'html.parser')

    manufacturer_tag = soup.find('div', class_='wl-attr--item pa_proizvoditel')
    manufacturer_value = manufacturer_tag.find('span', class_='pa-right') if manufacturer_tag else None
    manufacturer = manufacturer_value.get_text(strip=True) if manufacturer_value else 'Н/Д'

    return manufacturer

# Функция для парсинга одной страницы каталога
def parse_page(page_number):
    url = f'https://trast-zapchast.ru/shop/page/{page_number}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    start_time = time.time()  # Засекаем время начала парсинга страницы
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f'❌ Ошибка {response.status_code} при загрузке страницы {page_number}')
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = soup.find_all('div', class_='th-product-card')

    items = []
    for product in products:
        try:
            # Проверка на наличие класса "outofstock" или элемента, который указывает, что товар недоступен
            if product.find('a', class_='button product_type_variable'):
                continue

            # Изображение товара
            image_tag = product.find('div', class_='th-product-card__image').find('img')
            image_url = image_tag['src'] if image_tag else 'Н/Д'

            # Артикул (чистим от пробелов и тире)
            meta_tag = product.find('div', class_='th-product-card__meta')
            article_tag = meta_tag.find('span', class_='th-product-card__meta-value') if meta_tag else None
            # article = clean_article(article_tag.get_text(strip=True)) if article_tag else 'Н/Д'
            article = article_tag.get_text(strip=True) if article_tag else 'Н/Д'

            # Наименование
            name_tag = product.find('div', class_='th-product-card__name').find('h2')
            name = name_tag.get_text(strip=True) if name_tag else 'Н/Д'

            # Цена (чистим от символов)
            price_tag = product.find('div', class_='th-product-card__prices').find('span', class_='woocommerce-Price-amount')
            price = clean_price(price_tag.get_text(strip=True)) if price_tag else '0'

            # Ссылка на страницу товара
            product_page_tag = product.find('a', class_='woocommerce-LoopProduct-link')
            product_page_link = product_page_tag['href'] if product_page_tag else 'Н/Д'

            # Парсим страницу товара для получения производителя
            manufacturer = parse_product_page(product_page_link) if product_page_link != 'Н/Д' else 'Н/Д'

            items.append({
                'Наименование': name,
                'Производитель': manufacturer,
                'Артикул': article,
                'Цена': price,
                'Ссылка': product_page_link,
                'Изображение': image_url,
            })
            logger.info(f'✔️ Добавлен товар: {name} | Артикул: {article} | Цена: {price} | Производитель: {manufacturer}')
        except Exception as e:
            logger.warning(f'⚠️ Ошибка обработки товара на странице {page_number}: {e}')
            continue

    end_time = time.time()  # Засекаем время окончания парсинга страницы
    elapsed_time = round(end_time - start_time, 2)
    logger.info(f'📄 Парсим страницу {page_number}... 🕒 {elapsed_time} сек.')

    return items
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



# Основной процесс парсинга с многопоточностью
def main():
        try:
            with connect_to_db() as db_connection:
                # Устанавливаем начальный статус для XML и YML
                update_config_status(db_connection, "parser_status", "in_progress")
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                # Полная перезапись файла, если он существует
                if os.path.exists(OUTPUT_PATH):
                    os.remove(OUTPUT_PATH)
                    logger.info(f'🗑 Удалён старый файл: {OUTPUT_PATH}')

                start_time = datetime.now()  # Засекаем время начала всего парсинга
                logger.info(f'⏳ Начало парсинга: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')

                total_pages = get_total_pages()
                logger.info(f'🔍 Найдено страниц: {total_pages}')

                all_items = []

                # Создаём пул потоков для многозадачности
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_page = {executor.submit(parse_page, page): page for page in range(1, total_pages + 1)}

                    for future in as_completed(future_to_page):
                        page_number = future_to_page[future]
                        try:
                            items = future.result()
                            all_items.extend(items)
                            logger.info(f'✅ Страница {page_number} обработана.')
                        except Exception as e:
                            logger.warning(f'⚠️ Ошибка при обработке страницы {page_number}: {e}')

                df = pd.DataFrame(all_items, columns=['Наименование', 'Производитель', 'Артикул', 'Цена', 'Изображение', 'Ссылка'])

                df.to_excel(OUTPUT_PATH, sheet_name='Товары', index=False)

                end_time = datetime.now()  # Засекаем время окончания всего парсинга
                elapsed_time = end_time - start_time

                logger.info(f'✅ Парсинг завершен! Всего товаров собрано: {len(all_items)}')
                logger.info(f'📂 Данные сохранены в файл: {OUTPUT_PATH}')
                logger.info(f'⏳ Конец парсинга: {end_time.strftime("%Y-%m-%d %H:%M:%S")}')
                logger.info(f'⏱ Общее время работы: {elapsed_time}')
                update_config_status(db_connection, "parser_status", "done")
                update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
                logging.error(f"Ошибка при обработке обновлении цены: {e}")
                update_config_status(db_connection, "parser_status", "failed")
                update_config_status(db_connection, "parser_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# # Запуск скрипта
if __name__ == '__main__':
    main()
