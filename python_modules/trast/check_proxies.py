from proxy_manager import ProxyManager
import os

pm = ProxyManager()
print("Путь к файлу:", pm.proxies_file)
print("Существует ли файл:", os.path.exists(pm.proxies_file))

if os.path.exists(pm.proxies_file):
    import json
    with open(pm.proxies_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    protocols = {}
    for p in data:
        protocol = p.get('protocol', 'unknown')
        protocols[protocol] = protocols.get(protocol, 0) + 1
    
    print("Протоколы в кэше:", protocols)
    print("Всего прокси:", len(data))
else:
    print("Файл не существует, скачиваем прокси...")
    pm.download_proxies()
    print("Прокси скачаны")

