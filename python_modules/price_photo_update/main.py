import requests
import mysql.connector
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
import os
import certifi
import time
from datetime import datetime



# Пути для логов и XML
LOGS_PATH = "/home/admin/web/233204.fornex.cloud/public_html/storage/logs/update/"
XML_OUTPUT_PATH = "/home/admin/web/233204.fornex.cloud/public_html/public/"


# Настройка логирования

def setup_logging():
    # Уникальное имя файла для каждого запуска
    os.makedirs(LOGS_PATH, exist_ok=True)  # Создаем папку для логов, если ее нет
    log_filename = os.path.join(LOGS_PATH, f"update_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

    # Настройка логирования
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # Устанавливаем уровень логирования

    # Удаляем старые обработчики (если они есть)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Обработчик записи в файл
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Добавляем обработчики
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # Логируем успешное создание лог-файла
    logging.info(f"Логирование настроено. Файл лога: {log_filename}")

    return log_filename  # Возвращаем имя файла лога

def update_config_status(db_connection, name, value):
    """
    Обновляет значение в таблице config.
    Если записи с указанным name нет, она будет создана.
    """
    try:
        if not db_connection.is_connected():
            logging.error("Ошибка: соединение с базой данных отсутствует.")
            return
        
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


# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import xml.etree.ElementTree as ET

# Объединение файлов
def combine_xml_files(urls):
    combined_root = ET.Element('Ads')  # Создаем корневой элемент

    for url in urls:
        try:
            logging.info(f"Загружаем XML файл из {url}...")
            response = requests.get(url, verify=certifi.where())
            response.raise_for_status()
            xml_root = ET.fromstring(response.content)

            for ad in xml_root.findall('Ad'):
                combined_root.append(ad)  # Добавляем все <Ad> в общий корневой элемент

        except Exception as e:
            logging.error(f"Ошибка при загрузке или обработке файла из {url}: {e}")

    return combined_root


def cleanup_files():
    try:
        logging.info("Запуск очистки старых файлов...")

        # Список файлов, которые нужно удалить
        files_to_delete = [
            os.path.join(XML_OUTPUT_PATH, "avito_xml.xml"),
            os.path.join(XML_OUTPUT_PATH, "zzap_yml.xml"),
        ]

        for file_path in files_to_delete:
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"Удален файл: {file_path}")
            else:
                logging.info(f"Файл не найден (не требуется удалять): {file_path}")

        # Удаляем временные логи старше, например, 7 дней
        now = time.time()
        for filename in os.listdir(LOGS_PATH):
            file_path = os.path.join(LOGS_PATH, filename)
            if os.path.isfile(file_path):
                file_age = now - os.path.getmtime(file_path)
                if file_age > 7 * 24 * 60 * 60:  # 7 дней
                    os.remove(file_path)
                    logging.info(f"Удален старый лог: {file_path}")

        logging.info("Очистка завершена.")

    except Exception as e:
        logging.error(f"Ошибка при очистке файлов: {e}")


def combine_yml_files(urls):
    combined_root = ET.Element("yml_catalog", {"date": datetime.now().isoformat()})
    shop = None  # Переменная для хранения информации о магазине

    for url in urls:
        try:
            logging.info(f"Загружаем YML файл из {url}...")
            response = requests.get(url, verify=certifi.where())
            response.raise_for_status()
            xml_root = ET.fromstring(response.content)

            # Если магазин еще не добавлен, копируем из первого файла
            if shop is None:
                shop = xml_root.find('shop')
                if shop is not None:
                    combined_root.append(shop)

            # Копируем все <offer> из текущего файла
            offers = xml_root.find(".//offers")
            if offers is not None:
                combined_offers = combined_root.find(".//offers")
                if combined_offers is None:
                    combined_offers = ET.SubElement(shop, "offers")

                for offer in offers.findall("offer"):
                    combined_offers.append(offer)

        except Exception as e:
            logging.error(f"Ошибка при загрузке или обработке YML файла из {url}: {e}")

    return combined_root

def save_xml_with_formatting(root, filename):
    """
    Сохраняет отформатированный XML в XML_OUTPUT_PATH.
    """
    try:
        os.makedirs(XML_OUTPUT_PATH, exist_ok=True)  # Создаем папку для XML, если ее нет
        output_file = os.path.join(XML_OUTPUT_PATH, filename)

        # Добавляем отступы для форматирования XML
        ET.indent(root, space="    ", level=0)

        # Сохраняем XML
        tree = ET.ElementTree(root)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)

        logging.info(f"XML успешно сохранен в {output_file}")
        return output_file
    except Exception as e:
        logging.error(f"Ошибка при сохранении XML: {e}")
        return None
    
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

# Обновление фотографий
def update_photo(ad, db_connection):
    try:
        ad_id = ad.find('Id').text
        ad_id_parts = ad_id.split('_')
        if len(ad_id_parts) < 2:
            logging.warning(f"Некорректный формат Ad ID: {ad_id}")
            return

        brand, articul = ad_id_parts[0], ad_id_parts[1]

        # Получаем все возможные названия бренда
        valid_brands = get_matching_brands(brand, db_connection)
        logging.info(f"Варианты бренда {brand}: {valid_brands}")

        placeholders = ', '.join(['%s'] * len(valid_brands))
        query = f"""
            SELECT brand, articul
            FROM images
            WHERE LOWER(brand) IN ({placeholders}) AND LOWER(articul) LIKE %s
        """

        with db_connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (*valid_brands, f"{articul.lower()}%"))
            rows = cursor.fetchall()

        if not rows:
            logging.warning(f"Фото не найдено для Бренда: {brand}, Артикул: {articul}")
            return

        images = ad.find('Images')
        if images is None:
            images = ET.SubElement(ad, 'Images')

        for img in list(images):
            images.remove(img)

        for row in rows:
            img_url = f"https://233204.fornex.cloud/storage/uploads/{row['brand'].lower()}/{row['articul'].lower()}"
            new_image = ET.SubElement(images, 'Image')
            new_image.set('url', img_url)
            logging.info(f"Добавлено изображение: {img_url}")

    except Exception as e:
        logging.error(f"Ошибка в update_photo: {e}")

def update_photo_yml(offer, db_connection):
    try:
        vendor = offer.find('vendor').text
        vendor_code = offer.find('vendorCode').text

        # Получаем все возможные названия бренда
        valid_brands = get_matching_brands(vendor, db_connection)
        logging.info(f"Варианты бренда {vendor}: {valid_brands}")

        # Формируем запрос с плейсхолдерами
        placeholders = ', '.join(['%s'] * len(valid_brands))
        query = f"""
            SELECT brand, articul
            FROM images
            WHERE LOWER(brand) IN ({placeholders}) AND LOWER(articul) LIKE %s
        """

        with db_connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, (*valid_brands, f"{vendor_code.lower()}%"))
            rows = cursor.fetchall()

        if not rows:
            logging.warning(f"Фото не найдено для Бренда: {vendor}, Артикул: {vendor_code}")
            return False

        # Генерация списка URL-ов
        picture_urls = ",".join(
            f"https://233204.fornex.cloud/storage/uploads/{row['brand'].lower()}/{row['articul']}"
            for row in rows
        )

        # Обновление или создание тега <picture>
        picture_elem = offer.find('picture')
        if picture_elem is None:
            picture_elem = ET.SubElement(offer, 'picture')

        picture_elem.text = picture_urls
        logging.info(f"Добавлены фото для {vendor} {vendor_code}: {picture_urls}")

        return True
    except Exception as e:
        logging.error(f"Ошибка в update_photo_yml: {e}")
        return False

def get_matching_brands(brand, db_connection):
    try:
        with db_connection.cursor(dictionary=True) as cursor:
            query = """
                SELECT brand, sprav 
                FROM brand_sprav
                WHERE LOWER(brand) = LOWER(%s) OR LOWER(sprav) LIKE %s
            """
            cursor.execute(query, (brand, f"%{brand}%"))
            rows = cursor.fetchall()
        
        matching_brands = set()
        for row in rows:
            matching_brands.add(row['brand'].strip().lower())
            if row['sprav']:
                matching_brands.update([b.strip().lower() for b in row['sprav'].split('|')])

        return list(matching_brands) if matching_brands else [brand.lower()]
    except Exception as e:
        logging.error(f"Ошибка при получении брендов из справочника: {e}")
        return [brand.lower()]



def process_yml_catalog(root, db_connection):
    updated_offers_count = 0

    try:
        for offer in root.findall(".//offer"):
            vendor = offer.find('vendor').text  # Бренд
            vendor_code = offer.find('vendorCode').text  # Артикул

            logging.info(f"Обрабатываем Offer ID: {offer.get('id')}, Бренд: {vendor}, Артикул: {vendor_code}")

            # Обновляем цену
            price_updated = update_price_yml(offer, vendor, vendor_code, db_connection)

            # Обновляем фото
            photo_updated = update_photo_yml(offer, db_connection)

            # Увеличиваем счетчик, если хоть одно из значений было обновлено
            if price_updated or photo_updated:
                updated_offers_count += 1

    except Exception as e:
        logging.error(f"Ошибка при обработке yml_catalog: {e}")

    return updated_offers_count

# Update prices
def update_price(ad, brand, articul, db_connection):
    try:
        logging.info(f"Обновляем цену для: Brand = {brand}, Articul = {articul}")
        
        # Получаем список всех возможных вариантов брендов
        valid_brands = get_matching_brands(brand, db_connection)
        logging.info(f"Варианты бренда {brand}: {valid_brands}")
        
        api_login = os.getenv("API_LOGIN", "api@abcp50533")
        api_password = os.getenv("API_PASSWORD", "6f42e31351bc2469f37f27a7fa7da37c")
        url = "https://abcp50533.public.api.abcp.ru/search/articles"
        params = {
            "userlogin": api_login,
            "userpsw": api_password,
            "number": articul,
            "brand": brand
        }

        # Запрос к API
        response = requests.get(url, params=params, verify=certifi.where())
        response.raise_for_status()

        price_data = response.json()
        # logging.info(f"Ответ API для {brand} {articul}: {price_data}")

        if not price_data:
            logging.warning(f"Пустые данные для Brand = {brand}, Articul = {articul}")
            return

        for data in price_data:
            # logging.info(f"Проверяем данные: {data}")
            if (
                (str(data.get('distributorId')) == "1664240" or str(data.get('distributorId')) == "1696189") and 
                data.get('brand').lower() in [b.lower() for b in valid_brands] and
                data.get('numberFix').lower() == articul.lower()
            ):
                new_price_value = data.get('price')
                if new_price_value:
                    price_elem = ad.find('Price')
                    old_price = None
                    if price_elem is not None:
                        old_price = price_elem.text
                        ad.remove(price_elem)

                    new_price = ET.SubElement(ad, 'Price')
                    new_price.text = str(new_price_value)
                    logging.info(f"Цена обновлена для {brand} {articul}: старая цена = {old_price}, новая цена = {new_price_value}")
                    return

        logging.warning(f"Не найдено подходящих данных для обновления цены для {brand} {articul}.")
    except Exception as e:
        logging.error(f"Ошибка в update_price: {e}")

def update_price_yml(offer, vendor, vendor_code, db_connection):
    try:
        valid_brands = get_matching_brands(vendor, db_connection)
        logging.info(f"Варианты бренда {vendor}: {valid_brands}")

        api_login = os.getenv("API_LOGIN", "api@abcp50533")
        api_password = os.getenv("API_PASSWORD", "6f42e31351bc2469f37f27a7fa7da37c")
        url = "https://abcp50533.public.api.abcp.ru/search/articles"
        params = {
            "userlogin": api_login,
            "userpsw": api_password,
            "number": vendor_code,
            "brand": vendor
        }

        response = requests.get(url, params=params, verify=certifi.where())
        response.raise_for_status()

        price_data = response.json()

        # Поиск нужной цены
        for data in price_data:
            if (
                (str(data.get('distributorId')) == "1664240" or str(data.get('distributorId')) == "1696189") and
                data.get('brand').lower() in [b.lower() for b in valid_brands] and
                data.get('numberFix').lower() == vendor_code.lower()
            ):
                new_price = data.get('price')
                if new_price:
                    old_price = offer.find('price').text if offer.find('price') is not None else "N/A"
                    offer.find('price').text = str(new_price)  # Обновляем цену

                    logging.info(f"Цена обновлена для {vendor} {vendor_code}: старая цена = {old_price}, новая цена = {new_price}")
                    return True

        logging.warning(f"Не найдено подходящих данных для обновления цены для {vendor} {vendor_code}.")
        return False
    except Exception as e:
        logging.error(f"Ошибка в update_price_yml: {e}")
        return False

# Загрузка XML файла
def download_xml_file(url, output_file, timeout=30):
    try:
        logging.info("Начинаем загрузку XML файла...")
        with requests.get(url, stream=True, timeout=timeout, verify=certifi.where()) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            with open(output_file, 'wb') as file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        file.write(chunk)
                        downloaded_size += len(chunk)
                        percent_done = (downloaded_size / total_size) * 100 if total_size else 0
                        print(f"\rЗагрузка: {percent_done:.2f}%", end='')
        print("\nЗагрузка завершена успешно.")
        logging.info("XML файл успешно загружен.")
        return True
    except requests.exceptions.Timeout:
        logging.error("Ошибка: Превышено время ожидания подключения.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при загрузке файла: {e}")
    return False

# Основная функция обработки
def process_articles():
    try:
        with connect_to_db() as db_connection:
            # Устанавливаем начальный статус для XML и YML
            update_config_status(db_connection, "xml_update_status", "in_progress")
            update_config_status(db_connection, "yml_update_status", "in_progress")
            # update_config_status(db_connection, "parser_status", "in_progress")

            # Обработка XML
            try:
                urls_file_1 = [
                    "https://prdownload.nodacdn.net/dfiles/b6fc0d6b-296828-e63b6d87/articles.xml",
                    "https://prdownload.nodacdn.net/dfiles/7da749ad-284074-7b2184d7/articles.xml",
                ]
                combined_root_1 = combine_xml_files(urls_file_1)
                update_articles_and_save(combined_root_1, "avito_xml.xml")

                # Записываем время завершения обновления XML
                update_config_status(db_connection, "xml_update_status", "done")
                update_config_status(db_connection, "xml_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            except Exception as e:
                logging.error(f"Ошибка при обработке XML: {e}")
                update_config_status(db_connection, "xml_update_status", "failed")

            # Обработка YML
            try:
                urls_file_2 = [
                    "https://www.buszap.ru/get_price?p=219a76583bbd4991ade213a8b15b5808&FranchiseeId=9117065",
                    "https://www.buszap.ru/get_price?p=3dbb37d4f12242068faf72c2cf839c82&FranchiseeId=9117065",
                ]
                combined_root_2 = combine_yml_files(urls_file_2)
                updated_count = process_yml_catalog(combined_root_2, db_connection)
                save_xml_with_formatting(combined_root_2, "zzap_yml.xml")
                logging.info(f"Обновлено {updated_count} предложений во втором наборе.")

                # Записываем время завершения обновления YML
                update_config_status(db_connection, "yml_update_status", "done")
                update_config_status(db_connection, "yml_update_time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            except Exception as e:
                logging.error(f"Ошибка при обработке YML: {e}")
                update_config_status(db_connection, "yml_update_status", "failed")

    except Exception as e:
        logging.error(f"Критическая ошибка при выполнении процесса: {e}")

def update_articles_and_save(combined_root, output_file):
    try:
        # Подключение к базе данных
        updated_ads_count = 0  # Счетчик обновленных объявлений
        with connect_to_db() as db_connection:
            for ad in combined_root.findall('Ad'):
                ad_id = ad.find('Id').text
                logging.info(f"Обрабатываем Ad ID: {ad_id}")

                ad_id_parts = ad_id.split('_')
                if len(ad_id_parts) < 2:
                    logging.warning(f"Некорректный формат Ad ID: {ad_id}")
                    continue

                brand, articul = ad_id_parts[0], ad_id_parts[1]

                # Обновляем фото и цены
                update_photo(ad, db_connection)
                update_price(ad, brand, articul, db_connection)

                # Если дошли до этой строки, объявление обновлено
                updated_ads_count += 1

        # Сохраняем объединенный и отформатированный XML
        save_xml_with_formatting(combined_root, output_file)

        # Логируем количество обновленных объявлений
        logging.info(f"Количество обновленных объявлений в файле {output_file}: {updated_ads_count}")
    except Exception as e:
        logging.error(f"Ошибка в update_articles_and_save: {e}")

# Основная функция
def main():
    # Запускаем таймер
    start_time = time.time()
    
    # Настройка логирования
    log_file = setup_logging()
    # Очистка старых файлов перед началом
    cleanup_files()
    try:
        # Здесь выполняется основная логика программы
        process_articles()
    except Exception as e:
        logging.error(f"Ошибка выполнения программы: {e}")
    finally:
        # Остановка таймера
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Логируем время выполнения
        logging.info(f"Время выполнения скрипта: {elapsed_time:.2f} секунд.")
        logging.info(f"Лог завершен. Файл лога: {log_file}")

# Запуск основной функции
if __name__ == "__main__":
    main()

