from lxml import etree
import logging

def merge_xml(files, output_file):
    root = etree.Element("Ads", formatVersion="3", target="Avito.ru")
    total_ads = 0

    for file in files:
        tree = etree.parse(file)
        ads = tree.xpath("//Ad")
        count = len(ads)
        total_ads += count
        for ad in ads:
            root.append(ad)
        logging.info(f"Добавлено {count} тэгов <Ad> из файла: {file}")

    logging.info(f"Общее количество тэгов <Ad> после объединения: {total_ads}")

    tree = etree.ElementTree(root)
    tree.write(output_file, encoding="utf-8", pretty_print=True, xml_declaration=True)