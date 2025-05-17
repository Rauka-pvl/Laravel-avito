# zzap/zzap_merger.py
import os
import logging
import xml.etree.ElementTree as ET
from zzap_storage import url_to_filename
from config import COMBINED_ZZAP

def merge_yml_files(files: list[str]) -> ET.ElementTree:
    combined_root = ET.Element("yml_catalog", {"date": "2025-05-11T00:00:00"})
    shop = None
    total_offers = 0

    for filepath in files:
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()

            if shop is None:
                shop = root.find("shop")
                if shop is not None:
                    combined_shop = ET.SubElement(combined_root, "shop")
                    for child in list(shop):
                        if child.tag != "offers":
                            combined_shop.append(child)
                    offers_container = ET.SubElement(combined_shop, "offers")
                else:
                    logging.warning(f"Файл {filepath} не содержит тега <shop>")
                    continue
            else:
                offers_container = combined_root.find(".//offers")

            offers = root.findall(".//offer")
            for offer in offers:
                offers_container.append(offer)
            logging.info(f"Добавлено {len(offers)} тэгов <offer> из файла: {filepath}")
            total_offers += len(offers)

        except Exception as e:
            logging.error(f"Ошибка при обработке файла {filepath}: {e}")

    logging.info(f"Общее количество тэгов <offer> после объединения: {total_offers}")
    return ET.ElementTree(combined_root)

def save_merged_xml(tree: ET.ElementTree):
    tree.write(COMBINED_ZZAP, encoding="utf-8", xml_declaration=True)
    logging.info(f"Сохранён объединённый YML в файл: {COMBINED_ZZAP}")
