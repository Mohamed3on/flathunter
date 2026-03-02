"""Interface for webcrawlers. Crawler implementations should subclass this"""
from abc import ABC
import re

import backoff
import requests
# pylint: disable=unused-import
import requests_random_user_agent

from bs4 import BeautifulSoup

from flathunter import proxies
from flathunter.logging import logger
from flathunter.exceptions import ProxyException


class Crawler(ABC):
    """Defines the Crawler interface"""

    URL_PATTERN: re.Pattern

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

    def get_page(self, search_url, page_no=None) -> BeautifulSoup:
        """Applies a page number to a formatted search URL and fetches the exposes at that page"""
        return self.get_soup_from_url(search_url)

    @backoff.on_exception(wait_gen=backoff.constant,
                          exception=requests.exceptions.RequestException,
                          max_tries=3)
    def get_soup_from_url(self, url: str) -> BeautifulSoup:
        """Creates a Soup object from the HTML at the provided URL"""
        if self.config.use_proxy():
            return self.get_soup_with_proxy(url)

        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        if resp.status_code not in (200, 405):
            logger.error("Got response (%i): %s", resp.status_code, resp.content)

        return BeautifulSoup(resp.content, 'lxml')

    def get_soup_with_proxy(self, url) -> BeautifulSoup:
        """Will try proxies until it's possible to crawl and return a soup"""
        resolved = False
        resp = None

        while not resolved:
            proxies_list = proxies.get_proxies()
            for proxy in proxies_list:
                try:
                    resp = requests.get(
                        url,
                        headers=self.HEADERS,
                        proxies={"http": proxy, "https": proxy},
                        timeout=(20, 0.1)
                    )

                    if resp.status_code != 200:
                        logger.error("Got response (%i): %s",
                                     resp.status_code, resp.content)
                    else:
                        resolved = True
                        break

                except requests.exceptions.ConnectionError:
                    logger.error(
                        "Connection failed for proxy %s. Trying new proxy...", proxy)
                except requests.exceptions.Timeout:
                    logger.error(
                        "Connection timed out for proxy %s. Trying new proxy...", proxy
                    )
                except requests.exceptions.RequestException:
                    logger.error("Some error occurred. Trying new proxy...")

        if not resp:
            raise ProxyException(
                "An error occurred while fetching proxies or content")

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
        """Loads additional details for an expose. Should be implemented in the subclass"""
        return expose
