"""Expose crawler for Kleinanzeigen — pure requests (no Selenium)"""
import re
import datetime

import requests

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger

from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


class Kleinanzeigen(Crawler):
    """Implementation of Crawler interface for Kleinanzeigen (no Selenium)"""

    URL_PATTERN = re.compile(r'https://www\.kleinanzeigen\.de')

    def get_page(self, search_url, driver=None, page_no=None) -> BeautifulSoup:
        """Fetch search page via requests"""
        resp = requests.get(search_url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            logger.warning("Kleinanzeigen: got %d for %s", resp.status_code, search_url)
        return BeautifulSoup(resp.content, 'lxml')

    def get_expose_details(self, expose):
        expose['from'] = datetime.datetime.now().strftime('%02d.%m.%Y')
        return expose

    # pylint: disable=too-many-locals
    def extract_data(self, raw_data):
        """Extracts all exposes from a provided Soup object"""
        entries = []
        if raw_data is None:
            logger.warning("Kleinanzeigen: No page content received")
            return entries
        soup = raw_data.find(id="srchrslt-adtable")
        if soup is None:
            logger.warning("Kleinanzeigen: Could not find search results table - page may have changed or bot detection triggered")
            return entries

        exposes = soup.find_all("article", class_="aditem")
        for  expose in exposes:

            title_elem = expose.find(class_="ellipsis")
            if title_elem.get("href"):
                url = title_elem.get("href")
            else:
                continue

            try:
                price = expose.find(
                    class_="aditem-main--middle--price-shipping--price").text.strip()
                tags_element = expose.find(class_="aditem-main--middle--tags")
                address = expose.find("div", {"class": "aditem-main--top--left"})
                image_container = expose.find("div", {"class": "aditem-image"})
            except AttributeError as error:
                logger.warning("Unable to process Kleinanzeigen expose: %s", str(error))
                continue

            image = None
            if image_container is not None:
                img_tag = image_container.find("img")
                if img_tag is not None:
                    image = img_tag.get("src")

            address = address.text.strip()
            address = address.replace('\n', ' ').replace('\r', '')
            address = " ".join(address.split())

            size = ""
            rooms = ""
            if tags_element is not None:
                tags_text = tags_element.text.strip()
                size_match = re.search(r'(\d+)\s*m²', tags_text)
                if size_match:
                    size = size_match.group(1) + " m²"
                rooms_match = re.search(r'(\d+[.,]?\d*)\s*Zi\.?', tags_text)
                if rooms_match:
                    rooms = rooms_match.group(1)

            details = {
                'id': int(expose.get("data-adid")),
                'image': image,
                'url': ("https://www.kleinanzeigen.de" + url),
                'title': title_elem.text.strip(),
                'price': price,
                'size': size,
                'rooms': rooms,
                'address': address,
                'crawler': self.get_name()
            }
            entries.append(details)

        logger.debug('Number of entries found: %d', len(entries))

        return entries

    def load_address(self, url):
        """Extract address from expose — not available without JS, return empty"""
        return ""
