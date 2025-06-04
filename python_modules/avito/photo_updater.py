import os
import requests
import certifi
import logging
import xml.etree.ElementTree as ET
import mysql.connector
from config import COMBINED_XML

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

def get_matching_brands(brand: str, db):
    try:
        with db.cursor(dictionary=True) as cursor:
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

def update_photo(ad, db):
    try:
        ad_id = ad.find('Id').text
        ad_id_parts = ad_id.split('_')
        if len(ad_id_parts) < 2:
            logging.warning(f"Некорректный формат Ad ID: {ad_id}")
            return False

        brand, articul = ad_id_parts[0], ad_id_parts[1]
        valid_brands = get_matching_brands(brand, db)
        logging.info(f"Варианты бренда {brand}: {valid_brands}")

        if not valid_brands:
            logging.warning(f"Бренд не найден: {brand}")
            return False

        placeholders = ', '.join(['%s'] * len(valid_brands))
        query = f"""
            SELECT brand, articul
            FROM images
            WHERE LOWER(brand) IN ({placeholders}) AND LOWER(articul) LIKE %s
        """
        with db.cursor(dictionary=True) as cursor:
            cursor.execute(query, (*valid_brands, f"{articul.lower()}%"))
            rows = cursor.fetchall()

        if not rows:
            logging.warning(f"Фото не найдено для Бренда: {brand}, Артикул: {articul}")
            return False

        images = ad.find('Images')
        if images is None:
            images = ET.SubElement(ad, 'Images')
        else:
            for img in list(images):
                images.remove(img)

        for row in rows:
            img_url = f"https://233204.fornex.cloud/storage/uploads/{row['brand']}/{row['articul']}"
            new_image = ET.SubElement(images, 'Image')
            new_image.set('url', img_url)
            logging.info(f"Добавлено изображение: {img_url}")
        return True

    except Exception as e:
        logging.error(f"Ошибка в update_photo: {e}")
        return False


def update_price(ad, brand, articul, db_connection):
    try:
        logging.info(f"Обновляем цену для: Brand = {brand}, Articul = {articul}")

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

        response = requests.get(url, params=params, verify=certifi.where())
        response.raise_for_status()

        price_data = response.json()

        if not price_data:
            logging.warning(f"Пустые данные для Brand = {brand}, Articul = {articul}")
            return

        for data in price_data:
            if (
                (str(data.get('distributorId')) in ["1664240", "1696189"])
                and data.get('brand').lower() in [b.lower() for b in valid_brands]
                and data.get('numberFix').lower() == articul.lower()
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


def update_all_photos():
    updated_photo_count = 0
    updated_price_count = 0
    try:
        tree = ET.parse(COMBINED_XML)
        root = tree.getroot()
        db = connect_to_db()
        for ad in root.findall('Ad'):
            ad_id = ad.findtext('Id')
            ad_id_parts = ad_id.split('_')
            if len(ad_id_parts) < 2:
                logging.warning(f"Некорректный ID для цены и фото: {ad_id}")
                continue
            brand, articul = ad_id_parts[0], ad_id_parts[1]
            if update_photo(ad, db):
                updated_photo_count += 1
            if update_price(ad, brand, articul, db):
                updated_price_count += 1
            update_price(ad, brand, articul, db)
        tree.write(COMBINED_XML, encoding="utf-8", xml_declaration=True)
        logging.info(f"Всего обновлено фото: {updated_photo_count}, цен: {updated_price_count}")
        db.close()
        logging.info("Обновление изображений завершено")
    except Exception as e:
        logging.error(f"Ошибка при обработке XML: {e}")

