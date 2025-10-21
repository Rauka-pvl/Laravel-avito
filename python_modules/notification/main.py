import requests
import os
from dotenv import load_dotenv

# === Load .env ===
load_dotenv()

class TelegramNotifier:
    __BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    __USER_IDS = []
    
    @classmethod
    def _get_user_ids(cls):
        """Получает список ID пользователей из переменной окружения"""
        user_ids_str = os.getenv("TELEGRAM_USER_IDS", "")
        if user_ids_str and user_ids_str.strip():
            try:
                return list(map(int, user_ids_str.split(",")))
            except ValueError:
                return []
        return []
    
    @classmethod
    def notify(cls, text: str):
        """Отправляет уведомление в Telegram"""
        if not cls.__BOT_TOKEN:
            print(f"Telegram notification: {text}")
            return
            
        user_ids = cls._get_user_ids()
        if not user_ids:
            print(f"Telegram notification: {text}")
            return
            
        api_url = f"https://api.telegram.org/bot{cls.__BOT_TOKEN}/sendMessage"
        for user_id in user_ids:
            payload = {
                "chat_id": user_id,
                "text": text,
                "parse_mode": "HTML"
            }
            try:
                response = requests.post(api_url, json=payload)
                response.raise_for_status()
                print(f"[OK] Message sent to user {user_id}")
            except requests.RequestException as e:
                print(f"[ERROR] Failed to send message to user {user_id}: {e}")
