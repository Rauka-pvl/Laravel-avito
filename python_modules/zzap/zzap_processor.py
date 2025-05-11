# zzap/zzap_processor.py
import logging
import os
import sys
import requests
import certifi
import mysql.connector
import xml.etree.ElementTree as ET

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
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


def update_price_yml(offer, brand, article, db):
    try:
        valid_brands = get_matching_brands(brand, db)
        logging.info(f"Варианты бренда {brand}: {valid_brands}")

        params = {
            "userlogin": os.getenv("API_LOGIN", "api@abcp50533"),
            "userpsw": os.getenv("API_PASSWORD", "6f42e31351bc2469f37f27a7fa7da37c"),
            "number": article,
            "brand": brand
        }
        url = "https://abcp50533.public.api.abcp.ru/search/articles"

        response = requests.get(url, params=params, verify=certifi.where())
        response.raise_for_status()
        price_data = response.json()

        for data in price_data:
            if (
                str(data.get("distributorId")) in ["1664240", "1696189"] and
                data.get("brand", "").lower() in valid_brands and
                data.get("numberFix", "").lower() == article.lower()
            ):
                new_price = data.get("price")
                if new_price:
                    offer.find("price").text = str(new_price)
                    logging.info(f"Цена обновлена: {brand} {article} -> {new_price}")
                    return True

        logging.warning(f"Не удалось обновить цену: {brand} {article}")
        return False

    except Exception as e:
        logging.error(f"Ошибка при обновлении цены: {e}")
        return False

def update_picture_yml(offer, db):
    try:
        brand = offer.findtext("vendor")
        article = offer.findtext("vendorCode")
        valid_brands = get_matching_brands(brand, db)

        placeholders = ', '.join(['%s'] * len(valid_brands))
        query = f"""
            SELECT brand, articul
            FROM images
            WHERE LOWER(brand) IN ({placeholders}) AND LOWER(articul) LIKE %s
        """

        with db.cursor(dictionary=True) as cursor:
            cursor.execute(query, (*valid_brands, f"{article.lower()}%"))
            rows = cursor.fetchall()

        if not rows:
            logging.warning(f"Изображения не найдены: {brand} {article}")
            return False

        picture_elem = offer.find("picture")
        if picture_elem is None:
            picture_elem = ET.SubElement(offer, "picture")

        urls = [
            f"https://233204.fornex.cloud/storage/uploads/{row['brand'].lower()}/{row['articul'].lower()}"
            for row in rows
        ]
        picture_elem.text = ",".join(urls)
        logging.info(f"Обновлены изображения: {brand} {article} -> {picture_elem.text}")
        return True

    except Exception as e:
        logging.error(f"Ошибка при обновлении фото: {e}")
        return False

def process_combined_yml():
    updated = 0
    try:
        db = connect_to_db()
        tree = ET.parse(COMBINED_XML)
        root = tree.getroot()

        for offer in root.findall(".//offer"):
            brand = offer.findtext("vendor")
            article = offer.findtext("vendorCode")
            if not brand or not article:
                continue

            price_ok = update_price_yml(offer, brand, article, db)
            pic_ok = update_picture_yml(offer, db)

            if price_ok or pic_ok:
                updated += 1

        tree.write(COMBINED_XML, encoding="utf-8", xml_declaration=True)
        logging.info(f"Обновлено предложений: {updated}")
        db.close()
    except Exception as e:
        logging.error(f"Ошибка при обработке YML: {e}")
