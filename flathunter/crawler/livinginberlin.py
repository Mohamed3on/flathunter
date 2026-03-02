"""Expose crawler for livinginberlin.de"""
import re

from flathunter.abstract_crawler import Crawler
from flathunter.logging import logger

BASE_URL = "https://www.livinginberlin.de"


def _abs(href):
    """Make a relative URL absolute."""
    if href.startswith("http"):
        return href
    return f"{BASE_URL}/{href.lstrip('/')}"


def _parse_german_price(text):
    """'1.100,00 €' -> 1100.0"""
    m = re.search(r'[\d.]+,\d+', text)
    if not m:
        return None
    return float(m.group().replace('.', '').replace(',', '.'))


class LivingInBerlin(Crawler):
    """Implementation of Crawler interface for livinginberlin.de"""

    URL_PATTERN = re.compile(r'https://www\.livinginberlin\.de')

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
            href = _abs(href)

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
                    image = _abs(src)

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
                val = _parse_german_price(details["Gesamtmiete"])
                if val:
                    expose['warmmiete'] = val

            addr_parts = []
            if "Ort" in details:
                addr_parts.append(details["Ort"])
            if "Adresse" in details:
                addr_parts.append(details["Adresse"])
            if addr_parts:
                expose['address'] = ", ".join(addr_parts)

            # Description: substantial paragraphs
            desc_parts = []
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 60 and "cookie" not in text.lower():
                    desc_parts.append(text)
            if desc_parts:
                expose['detail_description'] = "\n".join(desc_parts)[:2000]

            # Photos from slideshow
            photos = []
            for a in soup.select("ul.uk-slideshow-items a[href]"):
                photos.append(_abs(a["href"]))
            photos = list(dict.fromkeys(photos))
            expose['detail_photos'] = photos
            expose['detail_total_photos'] = len(photos)

        except Exception as exc:
            logger.debug("Failed to fetch details for %s: %s", expose.get('url'), exc)
        return expose
