import os
import csv
import requests
import logging
from datetime import datetime
from io import BytesIO
from lxml import etree
from openpyxl import Workbook
from openpyxl.utils import get_column_letter


# === Импорт конфигурации из avito ===
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR


import os
import shutil
from datetime import datetime

# === Авторизация Froza ===
LOGIN = "SIVF"
PASSWORD = "Jmb08OVg7b"

# === Настройка логирования ===
os.makedirs(LOG_DIR, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = os.path.join(LOG_DIR, '..', "logs-froza",f"froza_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),  # Файл в UTF-8
        logging.StreamHandler(sys.stdout)  # Явно stdout
    ]
    
)
with open(log_filename, "w", encoding="utf-8-sig") as f:
    f.write("")  # Просто создаст файл с BOM
logging.FileHandler(log_filename, encoding="utf-8-sig")


# Попытка задать консоли нужную кодировку (Python 3.7+)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

logger = logging.getLogger(__name__)


# === XML-парсинг ответа Froza ===
def parse_xml_response(content):
    try:
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        tree = etree.parse(BytesIO(content), parser)
        root = tree.getroot()
        return [
            {child.tag: child.text for child in elem}
            for elem in root
        ] if root is not None else []
    except Exception as e:
        logger.error(f"Ошибка парсинга XML: {e}")
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

# === Выбор предложения с приоритетом <= 5 дней ===
def select_offer(data: list, oem: str = "", brand: str = "") -> tuple:
    fast, slow = [], []

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
        logger.info(f"Быстрое предложение: {chosen['price']} ₽, доставка {chosen['delivery_time']}–{chosen['delivery_time_guar']} дн.")
        return chosen, ""
    elif slow:
        slow.sort(key=lambda x: x[0])
        chosen = slow[0][1]
        logger.warning(f"Медленная доставка: {chosen['price']} ₽, {chosen['delivery_time']}–{chosen['delivery_time_guar']} дн.")
        return chosen, "Доставка > 5 дней"
    else:
        logger.warning(f"Нет предложений для {oem} ({brand})")
        return None, "Нет предложений"

# === Обработка XML-файла объявлений ===
def scan_ads_file(filepath: str) -> list:
    tree = etree.parse(filepath)
    ads = tree.xpath("//Ad")
    total = len(ads)
    logger.info(f"Найдено объявлений: {total}")

    results, processed, skipped = [], 0, 0

    for idx, ad in enumerate(ads, start=1):
        oem = ad.findtext("OEM")
        brand = ad.findtext("Brand")

        if oem and brand:
            logger.info(f"({idx}/{total}) Поиск: OEM={oem}, Brand={brand}")
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
            logger.warning(f"Пропущено объявление ({idx}/{total}): нет OEM или Brand")
            skipped += 1

    logger.info(f"Обработано: {processed}, Пропущено: {skipped}")
    return results

# === Сохранение в CSV ===
def save_to_csv(data: list, filename: str):
    if not data:
        logger.warning("Нет данных для сохранения.")
        return
    headers = ["Производитель", "Артикул", "Описание", "Цена", "Время доставки", "Комментарий"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"Результат сохранён в файл: {filename}")



# === Сохранение в XLSX ===
def save_to_xlsx(data: list, filename: str):
    if not data:
        logger.warning("Нет данных для сохранения.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Froza"

    headers = ["Производитель", "Артикул", "Описание", "Цена", "Время доставки", "Комментарий"]
    ws.append(headers)

    for row in data:
        ws.append([
            row.get("Производитель", ""),
            row.get("Артикул", ""),
            row.get("Описание", ""),
            row.get("Цена", ""),
            row.get("Время доставки", ""),
            row.get("Комментарий", "")
        ])

    # Автоширина колонок
    for i, col in enumerate(ws.columns, start=1):
        max_length = max((len(str(cell.value)) for cell in col if cell.value), default=10)
        ws.column_dimensions[get_column_letter(i)].width = min(max_length + 2, 50)

    wb.save(filename)
    logger.info(f"Результат сохранён в файл: {filename}")


# === Запуск ===
if __name__ == "__main__":
    xlsx_filename = os.path.join(os.path.dirname(COMBINED_XML), f"forza.xlsx")
    ads_data = scan_ads_file(COMBINED_XML)
    save_to_xlsx(ads_data, filename=xlsx_filename)
