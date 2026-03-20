"""Expose crawler for Kleinanzeigen — pure requests (no Selenium)"""
import re
import datetime

import requests
from bs4 import BeautifulSoup

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger

HTML_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


class Kleinanzeigen(Crawler):
    """Implementation of Crawler interface for Kleinanzeigen (no Selenium)"""

    URL_PATTERN = re.compile(r'https://www\.kleinanzeigen\.de')

    def get_page(self, search_url, page_no=None) -> BeautifulSoup:
        """Fetch search page via requests"""
        resp = requests.get(search_url, headers=HTML_HEADERS, timeout=20)
        if resp.status_code != 200:
            logger.warning("Kleinanzeigen: got %d for %s", resp.status_code, search_url)
        return BeautifulSoup(resp.content, 'lxml')

    def get_expose_details(self, expose):
        """Fetch description and photos from expose page"""
        expose['from'] = datetime.datetime.now().strftime('%d.%m.%Y')
        try:
            resp = requests.get(expose.get('url', ''), headers=HTML_HEADERS, timeout=15)
            if resp.status_code != 200:
                return expose
            soup = BeautifulSoup(resp.content, 'lxml')

            desc_el = soup.find('p', id='viewad-description-text')
            if desc_el:
                expose['detail_description'] = desc_el.get_text(separator="\n", strip=True)[:2000]

            photos = []
            for img in soup.select('#viewad-image img, .galleryimage img'):
                src = img.get('data-src') or img.get('src', '')
                if src and src.startswith('http'):
                    photos.append(src)
            self._set_photos(expose, photos)
        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
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
