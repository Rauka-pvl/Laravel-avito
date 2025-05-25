import requests

class TelegramNotifier:
    # === Внутренняя конфигурация ===
    # 551473803
    __BOT_TOKEN = "7699382439:AAEvlKvdDfy2nwbp8cWI_CtpLdB5qbtZCMY"
    __USER_IDS = [
        225913675,
        551473803
        ]

    @classmethod
    def notify(cls, text: str):
        pass
        # api_url = f"https://api.telegram.org/bot{cls.__BOT_TOKEN}/sendMessage"
        # for user_id in cls.__USER_IDS:
        #     payload = {
        #         "chat_id": user_id,
        #         "text": text,
        #         "parse_mode": "HTML"
        #     }
        #     try:
        #         response = requests.post(api_url, json=payload)
        #         response.raise_for_status()
        #         print(f"[OK] Сообщение отправлено пользователю {user_id}")
        #     except requests.RequestException as e:
        #         print(f"[ERROR] Не удалось отправить сообщение пользователю {user_id}: {e}")
