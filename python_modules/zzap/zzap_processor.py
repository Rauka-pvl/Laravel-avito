# zzap/zzap_processor.py
import logging
import os
import sys
import requests
import certifi
import mysql.connector
import xml.etree.ElementTree as ET

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_ZZAP

def connect_to_db():
    try:
        return mysql.connector.connect(
            host="127.0.0.1",
            user="uploader",
            password="uploader",
            database="avito"
        )
    except mysql.connector.Error as err:
        logging.error(f"Database connection error: {err}")
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
        logging.error(f"Error fetching brands from reference table: {e}")
        return [brand.lower()]

def update_price_yml(offer, brand, article, db):
    try:
        valid_brands = get_matching_brands(brand, db)
        logging.info(f"Brand variants for {brand}: {valid_brands}")

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
                    price_elem = offer.find("price")
                    old_price = price_elem.text if price_elem is not None else None

                    if price_elem is None:
                        price_elem = ET.SubElement(offer, "price")

                    price_elem.text = str(new_price)

                    logging.info(
                        f"Price updated: {brand} {article} | "
                        f"Old: {old_price} → New: {new_price}"
                    )
                    return True

        logging.warning(f"Price not updated: {brand} {article}")
        return False

    except Exception as e:
        logging.error(f"Error updating price: {e}")
        return False

def update_description_yml(offer, db):
    try:
        brand_elem = offer.find("vendor")
        article_elem = offer.find("vendorCode")
        desc_elem = offer.find("description")

        if brand_elem is None or article_elem is None:
            logging.warning(f"Missing <vendor> or <vendorCode> in offer: {ET.tostring(offer, encoding='unicode')}")
            return False

        brand = brand_elem.text.strip()
        articul = article_elem.text.strip()

        query = """
            SELECT i.*
            FROM intergrations i
            JOIN type_intergrations ti ON i.type_integration = ti.id
            WHERE LOWER(i.brand) = %s
              AND LOWER(i.article) = %s
              AND LOWER(ti.name) = 'zzap'
        """
        with db.cursor(dictionary=True) as cursor:
            cursor.execute(query, (brand.lower(), articul.lower()))
            row = cursor.fetchone()

        if not row:
            logging.info(f"No replacement found for Brand = {brand}, Article = {articul}")
            return False

        updated = False

        if row.get("brand_replace") and row["brand_replace"] != brand:
            logging.info(f"Replacing <vendor>: '{brand}' → '{row['brand_replace']}'")
            brand_elem.text = row["brand_replace"]
            updated = True

        if row.get("article_replace") and row["article_replace"] != articul:
            logging.info(f"Replacing <vendorCode>: '{articul}' → '{row['article_replace']}'")
            article_elem.text = row["article_replace"]
            updated = True

        if row.get("description_replace") and desc_elem is not None:
            base_text = desc_elem.text.strip() if desc_elem.text else ""
            desc_elem.text = base_text + " — " + row["description_replace"]
            logging.info(f"Appending to <description>: '{row['description_replace']}'")
            updated = True

        if updated:
            logging.info(f"Offer updated for Brand = {brand}, Article = {articul}")
        else:
            logging.info(f"No changes applied for Brand = {brand}, Article = {articul}")

        return updated

    except Exception as e:
        logging.error(f"Error in update_description_yml: {e}")
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
            logging.warning(f"No images found: {brand} {article}")
            return False

        picture_elem = offer.find("picture")
        if picture_elem is None:
            picture_elem = ET.SubElement(offer, "picture")

        urls = [
            f"https://233204.fornex.cloud/storage/uploads/{row['brand'].lower()}/{row['articul'].lower()}"
            for row in rows
        ]
        picture_elem.text = ",".join(urls)
        logging.info(f"Images updated: {brand} {article} → {picture_elem.text}")
        return True

    except Exception as e:
        logging.error(f"Error updating images: {e}")
        return False

def process_combined_yml():
    try:
        db = connect_to_db()
        tree = ET.parse(COMBINED_ZZAP)
        root = tree.getroot()

        offers = root.findall(".//offer")
        total = len(offers)
        updated = 0
        processed = 0

        logging.info(f"Total offers found: {total}")

        for idx, offer in enumerate(offers, 1):
            brand = offer.findtext("vendor")
            article = offer.findtext("vendorCode")
            if not brand or not article:
                logging.warning(f"[{idx}/{total}] Skipped: missing <vendor> or <vendorCode>")
                continue

            logging.info(f"[{idx}/{total}] Processing: Brand = {brand}, Article = {article}")

            desc_ok = update_description_yml(offer, db)
            price_ok = update_price_yml(offer, brand, article, db)
            pic_ok = update_picture_yml(offer, db)

            if desc_ok or price_ok or pic_ok:
                updated += 1
            processed += 1

        tree.write(COMBINED_ZZAP, encoding="utf-8", xml_declaration=True)
        logging.info(f"Processing completed. Processed: {processed}, Updated: {updated}, Skipped: {total - processed}")
        db.close()

    except Exception as e:
        logging.error(f"Error processing YML: {e}")
