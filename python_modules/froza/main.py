import os
import csv
import sys
import shutil
import logging
import requests
from io import BytesIO
from datetime import datetime
from lxml import etree
from openpyxl import Workbook
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from bz_telebot.database_manager import set_script_start, set_script_end
from openpyxl.utils import get_column_letter

# === Import configuration ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_XML, LOG_DIR
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from notification.main import TelegramNotifier

# === Froza credentials ===
LOGIN = "SIVF"
PASSWORD = "Jmb08OVg7b"

# === File paths for output and backup ===
OUTPUT_FILE = os.path.abspath(os.path.join(LOG_DIR, "..", "froza.xlsx"))
BACKUP_FILE = os.path.abspath(os.path.join(LOG_DIR, "..", "froza_backup.xlsx"))

# === Logging setup ===
def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_subdir = os.path.abspath(os.path.join(LOG_DIR, "..", "logs-froza"))
    os.makedirs(log_subdir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_subdir, f"froza_{timestamp}.log")
    with open(log_path, "w", encoding="utf-8-sig") as f:
        f.write("")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    return logging.getLogger("froza")

# === Parse XML response from Froza ===
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
        logger.error(f"XML parsing error: {e}")
        return []

# === Fetch price list from Froza ===
def get_price_list(code: str, brand: str = "") -> list:
    for attempt in [brand, ""]:
        url = f"https://www.froza.ru/search_xml4.php?get=price_list&user={LOGIN}&password={PASSWORD}&code={code}"
        if attempt:
            url += f"&brand={attempt}"

        try:
            logger.info(f"Requesting price list for: {code} (brand: {attempt or 'any'})")
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = parse_xml_response(response.content)
            if data:
                return data
        except Exception as e:
            logger.error(f"Request error: {e}")
    return []

# === Select the best offer (delivery <= 5 days) ===
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
        logger.info(f"Fast offer: {chosen['price']} RUB, delivery {chosen['delivery_time']}-{chosen['delivery_time_guar']} days")
        return chosen, ""
    elif slow:
        slow.sort(key=lambda x: x[0])
        chosen = slow[0][1]
        logger.warning(f"Slow delivery: {chosen['price']} RUB, {chosen['delivery_time']}-{chosen['delivery_time_guar']} days")
        return chosen, "Delivery > 5 days"
    else:
        logger.warning(f"No offers found for {oem} ({brand})")
        return None, "No offers found"

# === Scan XML ad file ===
def scan_ads_file(filepath: str) -> list:
    tree = etree.parse(filepath)
    ads = tree.xpath("//Ad")
    total = len(ads)
    logger.info(f"Total ads found: {total}")

    results, processed, skipped = [], 0, 0
    for idx, ad in enumerate(ads, start=1):
        oem = ad.findtext("OEM")
        brand = ad.findtext("Brand")

        if oem and brand:
            logger.info(f"({idx}/{total}) Searching: OEM={oem}, Brand={brand}")
            prices = get_price_list(oem, brand)
            offer, comment = select_offer(prices, oem=oem, brand=brand)
            results.append({
                "Manufacturer": brand,
                "Article": oem,
                "Description": offer.get("description_rus") if offer else "",
                "Price": offer.get("price") if offer else "",
                "Delivery Time": f"{offer.get('delivery_time')}–{offer.get('delivery_time_guar')} days" if offer else "",
                "Comment": comment or ""
            })
            processed += 1
        else:
            logger.warning(f"Skipped ad ({idx}/{total}): missing OEM or Brand")
            skipped += 1

    logger.info(f"Processed: {processed}, Skipped: {skipped}")
    return results

# === Save data to XLSX ===
def save_to_xlsx(data: list, filename: str):
    if not data:
        logger.warning("No data to save.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Froza"
    headers = ["Manufacturer", "Article", "Description", "Price", "Delivery Time", "Comment"]
    ws.append(headers)

    for row in data:
        ws.append([row.get(h, "") for h in headers])

    for i, col in enumerate(ws.columns, start=1):
        max_length = max((len(str(cell.value)) for cell in col if cell.value), default=10)
        ws.column_dimensions[get_column_letter(i)].width = min(max_length + 2, 50)

    wb.save(filename)
    logger.info(f"Saved result to file: {filename}")

# === Create Excel backup ===
def create_backup():
    if os.path.exists(OUTPUT_FILE):
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
        logger.info(f"Backup created: {BACKUP_FILE}")
    else:
        logger.info("Backup skipped: no output file found")

if __name__ == "__main__":
    script_name = "froza"
    TelegramNotifier.notify("Starting Froza processing")
    start_time = datetime.now()
    set_script_start(script_name)

    try:
        logger = setup_logging()
        create_backup()

        xlsx_filename = os.path.join(os.path.dirname(COMBINED_XML), "froza.xlsx")
        ads_data = scan_ads_file(COMBINED_XML)
        save_to_xlsx(ads_data, filename=xlsx_filename)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        set_script_end(script_name, status="done", duration=duration)

        TelegramNotifier.notify(
            f"Froza processing completed successfully. Duration: {duration:.2f} seconds."
        )

    except Exception as e:
        logging.exception("Error during processing:")
        set_script_end(script_name, status="failed")
        TelegramNotifier.notify(f"Error during Froza processing:\n<code>{str(e)}</code>")