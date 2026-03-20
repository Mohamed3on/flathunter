"""Interface for webcrawlers. Crawler implementations should subclass this"""
from abc import ABC
import re

import backoff
import requests
from bs4 import BeautifulSoup

from flathunter.logging import logger


class Crawler(ABC):
    """Defines the Crawler interface"""

    URL_PATTERN: re.Pattern
    BASE_URL: str | None = None

    HEADERS = {
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
        'Upgrade-Insecure-Requests': '1',
        'Accept': 'text/html,application/xhtml+xml,application/xml;'
                  'q=0.9,image/webp,image/apng,*/*;q=0.8,'
                  'application/signed-exchange;v=b3;q=0.9',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-User': '?1',
        'Sec-Fetch-Dest': 'document',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    def __init__(self, config):
        self.config = config

    def _abs(self, href):
        """Make a relative URL absolute using this crawler's BASE_URL."""
        if href.startswith("http"):
            return href
        return f"{self.BASE_URL}/{href.lstrip('/')}"

    def _extract_description(self, soup, max_len=2000, extra_excludes=()):
        """Extract description from long paragraphs, filtering boilerplate."""
        excludes = ('cookie',) + tuple(extra_excludes)
        parts = []
        for p in soup.find_all('p'):
            text = p.get_text(strip=True)
            lower = text.lower()
            if len(text) > 60 and not any(ex in lower for ex in excludes):
                parts.append(text)
        return "\n".join(parts)[:max_len] if parts else None

    def _set_photos(self, expose, photos):
        """Deduplicate photos and set detail_photos/detail_total_photos."""
        photos = list(dict.fromkeys(photos))
        expose['detail_photos'] = photos
        expose['detail_total_photos'] = len(photos)

    def get_page(self, search_url, page_no=None) -> BeautifulSoup:
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return self.get_soup_from_url(search_url)

    @backoff.on_exception(wait_gen=backoff.constant,
                          exception=requests.exceptions.RequestException,
                          max_tries=3)
    def get_soup_from_url(self, url: str) -> BeautifulSoup:
        """Creates a Soup object from the HTML at the provided URL"""
        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        if resp.status_code not in (200, 405):
            logger.error("Got response (%i): %s", resp.status_code, resp.content)

        return BeautifulSoup(resp.content, 'lxml')

    def extract_data(self, raw_data):
        """Should be implemented in subclass"""
        raise NotImplementedError

    def get_results(self, search_url, max_pages=None):
        """Loads the exposes from the site, starting at the provided URL"""
        logger.debug("Got search URL %s", search_url)

        soup = self.get_page(search_url)
        entries = self.extract_data(soup)
        logger.debug('Number of found entries: %d', len(entries))

        return entries

    def crawl(self, url, max_pages=None):
        """Load as many exposes as possible from the provided URL"""
        if re.search(self.URL_PATTERN, url):
            try:
                return self.get_results(url, max_pages)
            except requests.exceptions.ConnectionError:
                logger.warning(
                    "Connection to %s failed. Retrying.", url.split('/')[2])
                return []
        return []

    def get_name(self):
        """Returns the name of this crawler"""
        return type(self).__name__

    def get_expose_details(self, expose):
        """Enrich expose with detail_description, detail_photos, detail_total_photos,
        and optionally detail_contact_name / warmmiete. Subclasses should override."""
        return expose
