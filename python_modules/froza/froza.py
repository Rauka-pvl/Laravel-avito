import requests
from lxml import etree
from io import BytesIO
import logging
import csv

# === Авторизация ===
LOGIN = "SIVF"
PASSWORD = "Jmb08OVg7b"

# === Логирование ===
import os
from datetime import datetime

# === Папка для логов ===
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# === Имя лог-файла ===
log_filename = os.path.join(
    LOG_DIR,
    f"froza_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
)

# === Настройка логирования в консоль + файл ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# === XML-парсинг ответа от Froza ===
def parse_xml_response(content):
    try:
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(BytesIO(content), parser)
        root = tree.getroot()

        if root is None or not list(root):
            return []

        result = []
        for elem in root:
            item = {}
            for child in elem:
                item[child.tag] = child.text
            result.append(item)

        return result
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга XML: {e}")
        return []

# === Получение прайса от Froza ===
def get_price_list(code: str, brand: str = "") -> list:
    for attempt in [brand, ""]:
        url = f"https://www.froza.ru/search_xml4.php?get=price_list&user={LOGIN}&password={PASSWORD}&code={code}"
        if attempt:
            url += f"&brand={attempt}"

        try:
            logger.info(f"Получение прайс-листа для: {code} (бренд: {attempt or 'любой'})")
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = parse_xml_response(response.content)
            if data:
                return data
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
    return []

# === Поиск самой дешевой (с приоритетом <=5 дней) ===
def select_offer(data: list, oem: str = "", brand: str = "") -> tuple:
    fast = []
    slow = []

    for item in data:
        try:
            delivery_time = int(item.get("delivery_time", 999))
            price = float(item.get("price", 9999999))
            if delivery_time <= 5:
                fast.append((price, item))
            else:
                slow.append((price, item))
        except Exception:
            continue

    if fast:
        fast.sort(key=lambda x: x[0])
        chosen = fast[0][1]
        logger.info(f"✅ Найдена быстрая позиция: {chosen['price']} ₽, доставка {chosen['delivery_time']}–{chosen['delivery_time_guar']} дн. ({brand})")
        return chosen, ""
    elif slow:
        slow.sort(key=lambda x: x[0])
        chosen = slow[0][1]
        logger.warning(f"⚠️ Только медленная доставка: {chosen['price']} ₽, {chosen['delivery_time']}–{chosen['delivery_time_guar']} дн. ({brand})")
        return chosen, "Доставка > 5 дней"
    else:
        logger.warning(f"❗ Не найдено предложений для {oem} ({brand})")
        return None, "Нет предложений"

# === Сканирование XML-файла объявлений ===
def scan_ads_file(filepath: str) -> list:
    tree = etree.parse(filepath)
    ads = tree.xpath("//Ad")
    total = len(ads)
    logger.info(f"🔍 Найдено объявлений: {total}")
    
    results = []
    processed = 0
    skipped = 0

    for idx, ad in enumerate(ads, start=1):
        oem = ad.findtext("OEM")
        brand = ad.findtext("Brand")

        if oem and brand:
            logger.info(f"▶ ({idx}/{total}) Поиск по OEM={oem}, Brand={brand}")
            prices = get_price_list(oem, brand)
            offer, comment = select_offer(prices, oem=oem, brand=brand)
            if offer:
                results.append({
                    "Производитель": brand,
                    "Артикул": oem,
                    "Описание": offer.get("description_rus") or offer.get("description", ""),
                    "Цена": offer.get("price"),
                    "Время доставки": f"{offer.get('delivery_time')}–{offer.get('delivery_time_guar')} дн.",
                    "Комментарий": comment
                })
            else:
                results.append({
                    "Производитель": brand,
                    "Артикул": oem,
                    "Описание": "",
                    "Цена": "",
                    "Время доставки": "",
                    "Комментарий": "Нет предложений"
                })
            processed += 1
        else:
            logger.warning(f"⛔️ Пропущено объявление ({idx}/{total}): отсутствует OEM или Brand")
            skipped += 1

    logger.info(f"✅ Обработано: {processed}, ⛔ Пропущено: {skipped}")
    return results


# === Сохранение в CSV ===
def save_to_csv(data: list, filename: str = "result.csv"):
    if not data:
        logger.warning("Нет данных для сохранения.")
        return
    headers = ["Производитель", "Артикул", "Описание", "Цена", "Время доставки", "Комментарий"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"✅ Результат сохранён в файл: {filename}")

# === Запуск ===
if __name__ == "__main__":
    ads_data = scan_ads_file("avito_xml.xml")  # ← путь к XML-файлу
    save_to_csv(ads_data)
