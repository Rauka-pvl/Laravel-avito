import requests
import os
from dotenv import load_dotenv

# === Загрузка .env ===
load_dotenv()

class TelegramNotifier:
    __BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    __USER_IDS = list(map(int, os.getenv("TELEGRAM_USER_IDS", "").split(",")))

    @classmethod
    def notify(cls, text: str):
        api_url = f"https://api.telegram.org/bot{cls.__BOT_TOKEN}/sendMessage"
        for user_id in cls.__USER_IDS:
            payload = {
                "chat_id": user_id,
                "text": text,
                "parse_mode": "HTML"
            }
            try:
                response = requests.post(api_url, json=payload)
                response.raise_for_status()
                print(f"[OK] Сообщение отправлено пользователю {user_id}")
            except requests.RequestException as e:
                print(f"[ERROR] Не удалось отправить сообщение пользователю {user_id}: {e}")
