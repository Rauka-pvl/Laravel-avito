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
        logging.error(f"Database connection error: {err}")
        raise

def get_matching_brands(brand: str, db):
    try:
        with db.cursor(dictionary=True, buffered=True) as cursor:
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

def update_photo(ad, db):
    try:
        ad_id = ad.find('Id').text
        ad_id_parts = ad_id.split('_')
        if len(ad_id_parts) < 2:
            logging.warning(f"Invalid Ad ID format: {ad_id}")
            return False

        brand, articul = ad_id_parts[0], ad_id_parts[1]
        valid_brands = get_matching_brands(brand, db)
        logging.info(f"Brand variants for {brand}: {valid_brands}")

        if not valid_brands:
            logging.warning(f"Brand not found: {brand}")
            return False

        placeholders = ', '.join(['%s'] * len(valid_brands))
        query = f"""
            SELECT brand, articul
            FROM images
            WHERE LOWER(brand) IN ({placeholders}) AND LOWER(articul) LIKE %s
        """
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute(query, (*valid_brands, f"{articul.lower()}%"))
            rows = cursor.fetchall()

        if not rows:
            logging.warning(f"No images found for Brand: {brand}, Article: {articul}")
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
            logging.info(f"Image added: {img_url}")
        return True

    except Exception as e:
        logging.error(f"Error in update_photo: {e}")
        return False

def update_price(ad, brand, articul, db_connection):
    try:
        logging.info(f"Updating price for: Brand = {brand}, Article = {articul}")

        valid_brands = get_matching_brands(brand, db_connection)
        logging.info(f"Brand variants for {brand}: {valid_brands}")

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
            logging.warning(f"No data returned for Brand = {brand}, Article = {articul}")
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
                    logging.info(f"Price updated for {brand} {articul}: old = {old_price}, new = {new_price_value}")
                    return

        logging.warning(f"No matching price data found for {brand} {articul}.")
    except Exception as e:
        logging.error(f"Error in update_price: {e}")

def update_description(ad, db):
    try:
        brand_elem = ad.find('Brand')
        oem_elem = ad.find('OEM')
        desc_elem = ad.find('Description')

        if brand_elem is None or oem_elem is None:
            logging.warning(f"Missing <Brand> or <OEM> in ad: {ET.tostring(ad, encoding='unicode')}")
            return False

        brand = brand_elem.text.strip()
        articul = oem_elem.text.strip()

        query = """
            SELECT i.*
            FROM intergrations i
            JOIN type_intergrations ti ON i.type_integration = ti.id
            WHERE LOWER(i.brand) = %s
              AND LOWER(i.article) = %s
              AND LOWER(ti.name) = 'avito'
        """
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute(query, (brand.lower(), articul.lower()))
            row = cursor.fetchone()

        if not row:
            logging.info(f"No replacement found for Brand = {brand}, Article = {articul}")
            return False

        updated = False

        if row.get("brand_replace") and row["brand_replace"] != brand:
            logging.info(f"Replacing Brand: '{brand}' → '{row['brand_replace']}'")
            brand_elem.text = row["brand_replace"]
            updated = True

        if row.get("article_replace") and row["article_replace"] != articul:
            logging.info(f"Replacing OEM: '{articul}' → '{row['article_replace']}'")
            oem_elem.text = row["article_replace"]
            updated = True

        if row.get("description_replace") and desc_elem is not None:
            base_text = desc_elem.text.strip() if desc_elem.text else ""
            desc_elem.text = base_text + " — " + row["description_replace"]
            logging.info(f"Appending to <Description>: '{row['description_replace']}'")
            updated = True

        if updated:
            logging.info(f"Updated ad for Brand = {brand}, Article = {articul}")
        else:
            logging.info(f"No changes applied for Brand = {brand}, Article = {articul}")
        return updated

    except Exception as e:
        logging.error(f"Error in update_description: {e}")
        return False

def update_all_photos():
    updated_photo_count = 0
    updated_price_count = 0
    updated_description_count = 0
    try:
        tree = ET.parse(COMBINED_XML)
        root = tree.getroot()
        db = connect_to_db()
        for ad in root.findall('Ad'):
            ad_id = ad.findtext('Id')
            ad_id_parts = ad_id.split('_')
            if len(ad_id_parts) < 2:
                logging.warning(f"Invalid ID format for photo/price/description: {ad_id}")
                continue
            brand, articul = ad_id_parts[0], ad_id_parts[1]
            if update_description(ad, db):
                updated_description_count += 1
            if update_photo(ad, db):
                updated_photo_count += 1
            if update_price(ad, brand, articul, db):
                updated_price_count += 1
        tree.write(COMBINED_XML, encoding="utf-8", xml_declaration=True)
        logging.info(f"Update summary: photos = {updated_photo_count}, prices = {updated_price_count}, descriptions = {updated_description_count}")
        db.close()
        logging.info("Update process completed")
    except Exception as e:
        logging.error(f"Error processing XML: {e}")
