# zzap/zzap_merger.py
import os
import sys
from lxml import etree

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "avito")))
from config import COMBINED_ZZAP

def merge_yml_files(file_paths):
    combined_root = etree.Element("yml_catalog", date="now")
    shop_elem = None
    combined_offers = None

    for path in file_paths:
        try:
            tree = etree.parse(path)
            root = tree.getroot()
            shop = root.find("shop")
            offers = shop.find("offers") if shop is not None else None

            if shop is not None and shop_elem is None:
                shop_elem = etree.Element("shop")
                for child in shop:
                    if child.tag != "offers":
                        shop_elem.append(child)
                combined_offers = etree.SubElement(shop_elem, "offers")

            if offers is not None and combined_offers is not None:
                for offer in offers.findall("offer"):
                    combined_offers.append(offer)
        except Exception as e:
            print(f"[Ошибка] Не удалось обработать {path}: {e}")

    if shop_elem is not None:
        combined_root.append(shop_elem)
    return etree.ElementTree(combined_root)

def save_merged_xml(tree: etree.ElementTree):
    os.makedirs(os.path.dirname(COMBINED_ZZAP), exist_ok=True)
    tree.write(COMBINED_ZZAP, encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"[OK] Итоговый YML сохранён в {COMBINED_ZZAP}")
