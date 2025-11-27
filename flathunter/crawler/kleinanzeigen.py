"""Expose crawler for Kleinanzeigen"""
import re
import datetime

from bs4 import Tag

from flathunter.webdriver_crawler import WebdriverCrawler
from flathunter.logging import logger

class Kleinanzeigen(WebdriverCrawler):
    """Implementation of Crawler interface for Kleinanzeigen"""

    URL_PATTERN = re.compile(r'https://www\.kleinanzeigen\.de')
    MONTHS = {
        "Januar": "01",
        "Februar": "02",
        "März": "03",
        "April": "04",
        "Mai": "05",
        "Juni": "06",
        "Juli": "07",
        "August": "08",
        "September": "09",
        "Oktober": "10",
        "November": "11",
        "Dezember": "12"
    }

    def get_expose_details(self, expose):
        soup = self.get_page(expose['url'], self.get_driver())
        if soup is None:
            return expose
        for detail in soup.find_all('li', {"class": "addetailslist--detail"}):
            if re.match(r'Verfügbar ab', detail.text):
                date_string = re.match(r'(\w+) (\d{4})', detail.text)
                if date_string is not None:
                    expose['from'] = "01." + self.MONTHS[date_string[1]] + "." + date_string[2]
        if 'from' not in expose:
            expose['from'] = datetime.datetime.now().strftime('%02d.%02m.%Y')
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
                # If there is no title element, just continue since we can't provide an URL
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
        """Extract address from expose itself"""
        expose_soup = self.get_page(url)
        if expose_soup is None:
            return ""
        street_raw = ""
        street_el = expose_soup.find(id="street-address")
        if isinstance(street_el, Tag):
            street_raw = street_el.text
        address_raw = ""
        address_el = expose_soup.find(id="viewad-locality")
        if isinstance(address_el, Tag):
            address_raw = address_el.text

        return address_raw.strip().replace("\n", "") + " " + street_raw.strip()
