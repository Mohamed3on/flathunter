"""Package for notifiers."""
import requests

from flathunter.logging import logger

from .sender_apprise import SenderApprise
from .sender_telegram import SenderTelegram


def send_telegram_alert(bot_token: str, receiver_ids: list, text: str):
    """Send an HTML alert to Telegram receivers. Used for system notifications."""
    if not bot_token or not receiver_ids:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for chat_id in receiver_ids:
        try:
            requests.post(url, data={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }, timeout=10)
        except Exception as exc:
            logger.debug("Telegram alert failed for %s: %s", chat_id, exc)
