import os
import requests
import certifi
import pprint

brand = "FORD"         # замени при необходимости
articul = "1746967"    # замени при необходимости

api_login = os.getenv("API_LOGIN", "api@abcp50533")
api_password = os.getenv("API_PASSWORD", "6f42e31351bc2469f37f27a7fa7da37c")
url = "https://abcp50533.public.api.abcp.ru/search/articles"

params = {
    "userlogin": api_login,
    "userpsw": api_password,
    "number": articul,
    "brand": brand
}

try:
    print(f"Поиск цен для: Brand = {brand}, Article = {articul}")
    response = requests.get(url, params=params, verify=certifi.where())
    response.raise_for_status()
    data = response.json()

    if not data:
        print("Нет результатов от API.")
    else:
        print(f"Найдено {len(data)} предложений:")
        for idx, item in enumerate(data, 1):
            print(f"{idx}. Бренд: {item.get('brand')}, Артикул: {item.get('numberFix')}, "
                  f"Цена: {item.get('price')}, Дистрибьютор: {item.get('distributorId')}")

except Exception as e:
    print(f"Ошибка запроса: {e}")
