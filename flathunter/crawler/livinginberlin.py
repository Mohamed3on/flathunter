"""Expose crawler for livinginberlin.de"""
import re

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger
from flathunter.utils import parse_german_price


class LivingInBerlin(Crawler):
    """Implementation of Crawler interface for livinginberlin.de"""

    URL_PATTERN = re.compile(r'https://www\.livinginberlin\.de')
    BASE_URL = "https://www.livinginberlin.de"

    def extract_data(self, soup):
        entries = []
        for card in soup.select("div.uk-card.uk-card-default"):
            # URL from footer link or image link
            footer_link = card.select_one("div.uk-card-footer a[href]")
            if footer_link is None:
                continue
            href = footer_link.get("href", "")
            if "angebot" not in href:
                continue
            href = self._abs(href)

            id_match = re.search(r'/(\d+)$', href)
            if not id_match:
                continue
            expose_id = int(id_match.group(1))

            body = card.select_one("div.uk-card-body")
            if body is None:
                continue

            location = ""
            h3 = body.find("h3")
            if h3:
                location = h3.get_text(strip=True)

            title = ""
            p = body.find("p")
            if p:
                title = p.get_text(strip=True)

            # Parse "Zimmer:", "Wohnfläche:", "Kaltmiete:" from span.uk-text-muted + sibling text
            price = ""
            size = ""
            rooms = ""
            for span in body.select("span.uk-text-muted"):
                label = span.get_text(strip=True)
                value = span.next_sibling
                if value is None:
                    continue
                value = str(value).strip()
                if "Kaltmiete" in label:
                    price = value
                elif "Wohnfläche" in label:
                    size = value
                elif "Zimmer" in label:
                    rooms = value

            # Thumbnail from card-media-top
            image = None
            img = card.select_one("div.uk-card-media-top img")
            if img:
                src = img.get("data-src") or img.get("src")
                if src:
                    image = self._abs(src)

            entries.append({
                'id': expose_id,
                'url': href,
                'title': title,
                'price': price,
                'size': size,
                'rooms': rooms,
                'address': location,
                'image': image,
                'crawler': self.get_name(),
            })

        logger.debug('LivingInBerlin: found %d entries', len(entries))
        return entries

    def get_expose_details(self, expose):
        try:
            soup = self.get_soup_from_url(expose['url'])

            # dt/dd pairs from uk-description-list
            details = {}
            for dt in soup.select("dl.uk-description-list dt"):
                dd = dt.find_next_sibling("dd")
                if dd:
                    details[dt.get_text(strip=True)] = dd.get_text(strip=True)

            if "Gesamtmiete" in details:
                val = parse_german_price(details["Gesamtmiete"])
                if val:
                    expose['warmmiete'] = val

            addr_parts = []
            if "Ort" in details:
                addr_parts.append(details["Ort"])
            if "Adresse" in details:
                addr_parts.append(details["Adresse"])
            if addr_parts:
                expose['address'] = ", ".join(addr_parts)

            desc = self._extract_description(soup)
            if desc:
                expose['detail_description'] = desc

            # Photos from slideshow
            photos = []
            for a in soup.select("ul.uk-slideshow-items a[href]"):
                photos.append(self._abs(a["href"]))
            self._set_photos(expose, photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
