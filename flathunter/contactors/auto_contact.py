"""AutoContactProcessor — pipeline step that contacts landlords on matching listings"""
import random
from time import sleep

import requests

from flathunter.abstract_processor import Processor
from flathunter.contactors.wggesucht import WgGesuchtContactor
from flathunter.contactors.immoscout import ImmoscoutContactor
from flathunter.logging import logger

CONTACTOR_MAP = {
    "WgGesucht": WgGesuchtContactor,
    "Immobilienscout": ImmoscoutContactor,
}


class AutoContactProcessor(Processor):
    """Processor that auto-contacts landlords using Gemini-generated messages"""

    def __init__(self, config, id_watch):
        self.config = config
        self.id_watch = id_watch
        self.dry_run = config.auto_contact_dry_run()
        self.delay_min = config.auto_contact_delay_min()
        self.delay_max = config.auto_contact_delay_max()
        self._contactors = {}
        self._first_message = True
        self._alerted_cookies_expired = False

    def _get_contactor(self, crawler_name: str):
        if crawler_name not in self._contactors:
            cls = CONTACTOR_MAP.get(crawler_name)
            if cls is None:
                return None
            self._contactors[crawler_name] = cls(self.config)
        return self._contactors[crawler_name]

    def _send_telegram_alert(self, text: str):
        """Send an alert to the user via Telegram"""
        bot_token = self.config.telegram_bot_token()
        receiver_ids = self.config.telegram_receiver_ids()
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
            except Exception:
                pass

    def process_expose(self, expose):
        expose_id = expose.get('id')
        crawler = expose.get('crawler', '')

        if self.id_watch.is_contacted(expose_id, crawler):
            return expose

        # Kleinanzeigen: skip auto-contact (message shown in Telegram instead)
        if crawler == 'Kleinanzeigen':
            return expose

        # Use the Gemini-generated message from the score step
        message = expose.get('gemini_message')
        if not message:
            logger.debug("No contact message for expose %s (score too low or Gemini unavailable)", expose_id)
            return expose

        # Rate limit
        if not self._first_message:
            delay = random.uniform(self.delay_min, self.delay_max)
            logger.debug("Sleeping %.1fs before next contact", delay)
            sleep(delay)
        self._first_message = False

        if self.dry_run:
            logger.info("[DRY RUN] Would send to %s (expose %s on %s):\n%s",
                        expose.get('url'), expose_id, crawler, message)
            return expose

        contactor = self._get_contactor(crawler)
        if contactor is None:
            logger.debug("No contactor for crawler %s", crawler)
            return expose

        if contactor.send_message(expose, message):
            self.id_watch.mark_contacted(expose_id, crawler)
            logger.info("Contacted landlord for expose %s on %s", expose_id, crawler)
            self._send_telegram_alert(
                f"✅ <b>Auto-contact sent</b>\n"
                f"{expose.get('title', 'N/A')}\n"
                f"Score: {expose.get('gemini_score', '?')}/10\n"
                f"{expose.get('url', '')}"
            )
        else:
            logger.warning("Failed to contact landlord for expose %s on %s", expose_id, crawler)
            # Check for cookie expiry (ImmoScout specific)
            if hasattr(contactor, 'cookies_expired') and contactor.cookies_expired:
                if not self._alerted_cookies_expired:
                    self._send_telegram_alert(
                        "🚨 <b>ImmoScout session cookies expired!</b>\n"
                        "Auto-contact is broken. Update immoscout_session_cookies "
                        "in config.yaml with fresh cookies from your browser."
                    )
                    self._alerted_cookies_expired = True
            else:
                self._send_telegram_alert(
                    f"❌ <b>Auto-contact failed</b>\n"
                    f"{crawler} expose {expose_id}\n"
                    f"{expose.get('url', '')}"
                )

        return expose
