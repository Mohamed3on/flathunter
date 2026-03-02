"""ImmoScout24 contactor — pure requests via web API, with auto cookie refresh"""
import re
import time

import requests

from flathunter.contactors import AbstractContactor
from flathunter.logging import logger


class ImmoscoutContactor(AbstractContactor):
    """Contact landlords on ImmoScout24 via web API.

    When session cookies or the AWS WAF token expire, attempts automatic
    recovery via 2captcha (for WAF challenges) and/or SSO re-login.
    """

    def __init__(self, config):
        details = config.auto_contact_immoscout()
        self.first_name = details.get('first_name', '')
        self.last_name = details.get('last_name', '')
        self.email = details.get('email', '')
        self.phone = details.get('phone', '')
        self.street = details.get('street', '')
        self.house_number = details.get('house_number', '')
        self.postcode = details.get('postcode', '')
        self.city = details.get('city', '')
        self.config = config
        self._session = None
        self.cookies_expired = False

    # ── session management ──────────────────────────────────────────

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/145.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.immobilienscout24.de",
            })
            cookie_str = self.config.immoscout_session_cookies()
            if cookie_str:
                for part in cookie_str.split(';'):
                    part = part.strip()
                    if '=' not in part:
                        continue
                    name, value = part.split('=', 1)
                    self._session.cookies.set(name.strip(), value.strip(),
                                              domain='.immobilienscout24.de')
        return self._session

    def is_logged_in(self) -> bool:
        return bool(self.config.immoscout_session_cookies())

    def login(self) -> bool:
        return self.is_logged_in()

    # ── 2captcha helpers ────────────────────────────────────────────

    def _submit_to_2captcha(self, params: dict) -> str | None:
        """Submit a captcha to 2captcha and poll for the solution."""
        api_key = self.config.twocaptcha_api_key()
        if not api_key:
            return None

        params['key'] = api_key
        params['json'] = 1

        try:
            resp = requests.post('https://2captcha.com/in.php', data=params, timeout=30)
            data = resp.json()
            if data.get('status') != 1:
                logger.error("2captcha submit error: %s", data.get('request'))
                return None
            captcha_id = data['request']
        except Exception as exc:
            logger.error("2captcha submit failed: %s", exc)
            return None

        # Poll for result (up to 3 min)
        for _ in range(36):
            time.sleep(5)
            try:
                result = requests.get(
                    'https://2captcha.com/res.php',
                    params={'key': api_key, 'action': 'get', 'id': captcha_id, 'json': 1},
                    timeout=30,
                )
                data = result.json()
                if data.get('status') == 1:
                    return data['request']
                if data.get('request') != 'CAPCHA_NOT_READY':
                    logger.error("2captcha error: %s", data.get('request'))
                    return None
            except Exception as exc:
                logger.error("2captcha poll failed: %s", exc)
                return None

        logger.error("2captcha: timeout waiting for solution")
        return None

    # ── AWS WAF challenge ───────────────────────────────────────────

    def _is_waf_challenge(self, resp: requests.Response) -> bool:
        return resp.status_code == 405 or 'awswaf-captcha' in resp.text[:5000]

    def _solve_aws_waf(self, challenge_html: str, page_url: str) -> str | None:
        """Extract WAF challenge params, solve via 2captcha, return the token."""
        sitekey_match = re.search(r'apiKey:\s*["\']([^"\']+)', challenge_html)
        challenge_js_match = re.search(r'src="([^"]*challenge\.js[^"]*)"', challenge_html)

        if not sitekey_match or not challenge_js_match:
            logger.error("ImmoScout: WAF challenge params not found in page")
            return None

        sitekey = sitekey_match.group(1)
        challenge_url = challenge_js_match.group(1)
        base_url = challenge_url.rsplit('/challenge.js', 1)[0]

        # Fetch the challenge problem to get iv + context
        try:
            resp = requests.get(f"{base_url}/v2/problem?key={sitekey}", timeout=15)
            problem = resp.json()
            iv = problem.get('state', {}).get('iv')
            context = problem.get('state', {}).get('payload')
        except Exception as exc:
            logger.error("ImmoScout: WAF problem request failed: %s", exc)
            return None

        if not iv or not context:
            logger.error("ImmoScout: WAF challenge missing iv/context")
            return None

        logger.info("ImmoScout: submitting WAF challenge to 2captcha")
        return self._submit_to_2captcha({
            'method': 'amazon_waf',
            'sitekey': sitekey,
            'iv': iv,
            'context': context,
            'challenge_script': challenge_url,
            'pageurl': page_url,
        })

    def _handle_waf_challenge(self, resp: requests.Response, url: str) -> bool:
        """Solve WAF challenge and update session cookie. Returns True on success."""
        token = self._solve_aws_waf(resp.text, url)
        if not token:
            return False
        self._get_session().cookies.set(
            'aws-waf-token', token, domain='.immobilienscout24.de')
        logger.info("ImmoScout: WAF token refreshed via 2captcha")
        return True

    # ── nonce extraction with auto-refresh ──────────────────────────

    def _extract_nonce(self, expose_id: str) -> str | None:
        """Fetch expose page and extract nonceToken.
        Automatically solves AWS WAF challenges via 2captcha."""
        self.cookies_expired = False
        session = self._get_session()
        url = f"https://www.immobilienscout24.de/expose/{expose_id}"

        try:
            resp = session.get(url, timeout=15, allow_redirects=False)

            # ── AWS WAF challenge ──
            if self._is_waf_challenge(resp):
                logger.info("ImmoScout: WAF challenge on expose %s", expose_id)
                if self._handle_waf_challenge(resp, url):
                    resp = session.get(url, timeout=15, allow_redirects=False)
                else:
                    logger.error("ImmoScout: WAF challenge unsolvable")
                    self.cookies_expired = True
                    return None

            # ── auth redirect / session expired ──
            if resp.status_code in (401, 403) or (
                    resp.status_code in (301, 302)
                    and 'sso' in resp.headers.get('Location', '').lower()):
                logger.error("ImmoScout: session expired (HTTP %d)", resp.status_code)
                self.cookies_expired = True
                return None

            if resp.status_code != 200:
                logger.error("ImmoScout: page fetch %d for %s", resp.status_code, expose_id)
                return None

            # ── login redirect in HTML ──
            if 'sso/login' in resp.text[:5000] and 'nonceToken' not in resp.text:
                logger.error("ImmoScout: session cookies expired (login redirect in page)")
                self.cookies_expired = True
                return None

            match = re.search(r'"nonceToken":\s*"([^"]+)"', resp.text)
            if match:
                return match.group(1)
            logger.error("ImmoScout: nonceToken not found for %s", expose_id)
        except Exception as exc:
            logger.error("ImmoScout: page fetch failed for %s: %s", expose_id, exc)
        return None

    # ── send message ────────────────────────────────────────────────

    def send_message(self, expose: dict, message: str) -> bool:
        expose_id = str(expose.get('id', ''))

        if not self.config.immoscout_session_cookies():
            logger.error("ImmoScout: no session cookies configured")
            return False

        nonce = self._extract_nonce(expose_id)
        if not nonce:
            return False

        session = self._get_session()
        url = f"https://www.immobilienscout24.de/expose/{expose_id}"
        payload = {
            "suspiciousRequest": False,
            "sendUserProfile": True,
            "userProfileExists": True,
            "privacyPolicyAccepted": False,
            "sendButtonDelay": 3000,
            "personalData": {
                "salutation": "MALE",
                "firstName": self.first_name,
                "lastName": self.last_name,
                "emailAddress": self.email,
                "phoneNumber": self.phone,
                "message": message,
                "street": self.street,
                "houseNumber": self.house_number,
                "postcode": self.postcode,
                "city": self.city,
                "hasPets": False,
                "numberOfPersons": "FAMILY",
                "moveInDateType": "FLEXIBLE",
                "moveInDate": None,
                "employmentRelationship": "PUBLIC_EMPLOYEE",
                "income": "OVER_5000",
                "applicationPackageCompleted": True,
            },
            "isFromCounterOfferModal": False,
            "nonceToken": nonce,
            "isTenantNetworkListing": False,
            "reCaptchaToken": "",
        }

        try:
            resp = session.post(url, json=payload, headers={
                "Content-Type": "application/json",
                "Referer": url,
            }, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                if data.get("successful"):
                    logger.info("ImmoScout: contact sent for expose %s", expose_id)
                    return True
                logger.error("ImmoScout: API returned unsuccessful for %s: %s",
                             expose_id, resp.text[:300])
            else:
                logger.error("ImmoScout: POST %d for %s: %s",
                             resp.status_code, expose_id, resp.text[:300])
        except Exception as exc:
            logger.error("ImmoScout: POST failed for %s: %s", expose_id, exc)
        return False
