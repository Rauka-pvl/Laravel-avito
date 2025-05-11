import logging
import xml.etree.ElementTree as ET
import requests
import certifi
import os

def combine_yml_files(urls):
    combined_root = ET.Element("yml_catalog", {"date": "now"})
    shop = None

    for url in urls:
        try:
            logging.info(f"Загружаем YML файл из {url}...")
            response = requests.get(url, verify=certifi.where())
            response.raise_for_status()
            xml_root = ET.fromstring(response.content)

            if shop is None:
                shop = xml_root.find('shop')
                if shop is not None:
                    combined_root.append(shop)

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


def update_photo_yml(offer, db_connection, get_matching_brands):
    try:
        vendor = offer.find('vendor').text
        vendor_code = offer.find('vendorCode').text

        valid_brands = get_matching_brands(vendor, db_connection)
        logging.info(f"Варианты бренда {vendor}: {valid_brands}")

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
            logging.warning(f"Фото не найдено для {vendor} {vendor_code}")
            return False

        picture_urls = ",".join(
            f"https://233204.fornex.cloud/storage/uploads/{row['brand'].lower()}/{row['articul']}"
            for row in rows
        )

        picture_elem = offer.find('picture')
        if picture_elem is None:
            picture_elem = ET.SubElement(offer, 'picture')

        picture_elem.text = picture_urls
        logging.info(f"Добавлены фото: {picture_urls}")
        return True
    except Exception as e:
        logging.error(f"Ошибка в update_photo_yml: {e}")
        return False


def update_price_yml(offer, vendor, vendor_code, db_connection, get_matching_brands):
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
        for data in price_data:
            if (
                (str(data.get('distributorId')) in ["1664240", "1696189"]) and
                data.get('brand').lower() in [b.lower() for b in valid_brands] and
                data.get('numberFix').lower() == vendor_code.lower()
            ):
                new_price = data.get('price')
                if new_price:
                    price_elem = offer.find('price')
                    old_price = price_elem.text if price_elem is not None else "N/A"
                    if price_elem is None:
                        price_elem = ET.SubElement(offer, 'price')
                    price_elem.text = str(new_price)
                    logging.info(f"Цена обновлена: {vendor} {vendor_code}, {old_price} → {new_price}")
                    return True
        logging.warning(f"Цена не найдена для {vendor} {vendor_code}")
        return False
    except Exception as e:
        logging.error(f"Ошибка в update_price_yml: {e}")
        return False


def process_yml_catalog(root, db_connection, get_matching_brands):
    updated_count = 0
    try:
        for offer in root.findall(".//offer"):
            vendor = offer.findtext('vendor')
            vendor_code = offer.findtext('vendorCode')
            if not vendor or not vendor_code:
                continue

            logging.info(f"Обработка предложения: {vendor} {vendor_code}")
            price_updated = update_price_yml(offer, vendor, vendor_code, db_connection, get_matching_brands)
            photo_updated = update_photo_yml(offer, db_connection, get_matching_brands)

            if price_updated or photo_updated:
                updated_count += 1
    except Exception as e:
        logging.error(f"Ошибка в process_yml_catalog: {e}")
    return updated_count
