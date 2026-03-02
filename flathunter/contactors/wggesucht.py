"""WG-Gesucht contactor — pure requests-based session login + API messaging"""
import re

import requests
from bs4 import BeautifulSoup

from flathunter.contactors import AbstractContactor
from flathunter.logging import logger


class WgGesuchtContactor(AbstractContactor):
    """Send messages to WG-Gesucht landlords via their internal API"""

    LOGIN_URL = "https://www.wg-gesucht.de/ajax/api/Smp/api.php?action=login"
    CONVERSATIONS_URL = "https://www.wg-gesucht.de/ajax/api/Smp/api.php?action=conversations"

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://www.wg-gesucht.de',
    }

    def __init__(self, config):
        creds = config.auto_contact_wg_gesucht()
        self.email = creds.get('email', '')
        self.password = creds.get('password', '')
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._logged_in = False

    def is_logged_in(self) -> bool:
        return self._logged_in

    def login(self) -> bool:
        if not self.email or not self.password:
            logger.error("WG-Gesucht: no credentials configured")
            return False
        try:
            # Load homepage first to get cookies
            self.session.get("https://www.wg-gesucht.de/", timeout=15)

            resp = self.session.post(self.LOGIN_URL, json={
                "login_email_username": self.email,
                "login_password": self.password,
                "login_form_auto_login": "1",
                "display_language": "de",
            }, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("user_id"):
                    self._logged_in = True
                    logger.info("WG-Gesucht: logged in as user %s", data["user_id"])
                    return True
                logger.error("WG-Gesucht login failed: %s", data)
            else:
                logger.error("WG-Gesucht login HTTP %d", resp.status_code)
        except Exception as e:
            logger.error("WG-Gesucht login error: %s", e)
        return False

    def _get_form_tokens(self, expose_url: str) -> dict:
        """Load the listing page and extract messaging form tokens"""
        resp = self.session.get(expose_url, timeout=15)
        soup = BeautifulSoup(resp.content, 'lxml')

        form = soup.find('form', id='messenger_form') or soup.find('div', id='messenger_form')
        if not form:
            # Try finding tokens in hidden inputs anywhere on the page
            form = soup

        tokens = {}
        for field in ('user_id', 'ad_type', 'ad_id', 'csrf_token'):
            el = form.find('input', {'name': field})
            if el:
                tokens[field] = el.get('value', '')

        # Fallback: extract csrf_token from meta tag
        if 'csrf_token' not in tokens:
            meta = soup.find('meta', {'name': 'csrf-token'})
            if meta:
                tokens['csrf_token'] = meta.get('content', '')

        # Fallback: extract ad_id from URL
        if 'ad_id' not in tokens:
            match = re.search(r'\.(\d+)\.html', expose_url)
            if match:
                tokens['ad_id'] = match.group(1)

        return tokens

    def send_message(self, expose: dict, message: str) -> bool:
        if not self._logged_in and not self.login():
            return False

        url = expose.get('url', '')
        tokens = self._get_form_tokens(url)
        required = ('user_id', 'ad_type', 'ad_id', 'csrf_token')
        if not all(tokens.get(k) for k in required):
            logger.error("WG-Gesucht: missing form tokens for %s: got %s", url, tokens)
            return False

        payload = {
            "user_id": tokens['user_id'],
            "csrf_token": tokens['csrf_token'],
            "ad_type": tokens['ad_type'],
            "ad_id": tokens['ad_id'],
            "messages": [{"content": message, "message_type": "text"}],
        }

        try:
            resp = self.session.post(self.CONVERSATIONS_URL, json=payload, timeout=15)
            data = resp.json()
            if data.get('conversation_id'):
                logger.info("WG-Gesucht: sent message, conversation_id=%s", data['conversation_id'])
                return True
            logger.error("WG-Gesucht: send failed: %s", data)
        except Exception as e:
            logger.error("WG-Gesucht: send error: %s", e)
        return False
