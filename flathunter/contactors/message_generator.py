"""Score listings and generate contact messages using Gemini 3 Flash Preview"""
import json
import re
import base64
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from flathunter.logging import logger

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1alpha/models/gemini-3-flash-preview:generateContent"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "message": {"type": "string", "nullable": True},
    },
    "required": ["score", "pros", "cons", "summary", "message"],
}


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

MAX_PHOTOS = 3


def _fetch_image_as_base64(url: str) -> Optional[dict]:
    """Download an image and return as inline_data part for Gemini"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        content_type = resp.headers.get('content-type', 'image/jpeg')
        if 'image' not in content_type:
            content_type = 'image/jpeg'
        return {
            "inline_data": {
                "mime_type": content_type,
                "data": base64.b64encode(resp.content).decode('utf-8')
            }
        }
    except Exception:
        return None


IMMOSCOUT_API_HEADERS = {
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "ImmoScout_27.3_26.0_._",
}


def _fetch_detail_page(expose: dict) -> dict:
    """Fetch listing details: description + photo URLs.
    Uses mobile API for ImmoScout, HTML scraping for others."""
    url = expose.get('url', '')
    crawler = expose.get('crawler', '').lower()
    result = {'description': '', 'photo_urls': [], 'total_photos': 0}

    try:
        if 'immobilienscout' in crawler or 'immobilienscout24' in url:
            result = _fetch_immoscout_detail(expose)
        elif 'wg-gesucht' in crawler or 'wg-gesucht' in url:
            result = _fetch_html_detail(expose, _parse_wggesucht)
        elif 'kleinanzeigen' in crawler or 'kleinanzeigen' in url:
            result = _fetch_html_detail(expose, _parse_kleinanzeigen)
    except Exception as e:
        logger.debug("Could not fetch detail page for %s: %s", url, e)

    return result


def _fetch_immoscout_detail(expose: dict) -> dict:
    """Use ImmoScout mobile API for expose details — returns description + photos."""
    expose_id = expose.get('id', '')
    result = {'description': '', 'photo_urls': [], 'total_photos': 0}

    resp = requests.get(
        f"https://api.mobile.immobilienscout24.de/expose/{expose_id}",
        headers=IMMOSCOUT_API_HEADERS, timeout=15)
    if resp.status_code != 200:
        return result

    data = resp.json()
    descriptions = []
    photos = []

    # Extract contact name
    try:
        agent_name = data.get('contact', {}).get('contactData', {}).get('agent', {}).get('name', '')
        if agent_name:
            result['contact_name'] = agent_name
    except Exception:
        pass

    for section in data.get('sections', []):
        stype = section.get('type')
        if stype == 'TEXT_AREA':
            title = section.get('title', '')
            text = section.get('text', '')
            if text:
                descriptions.append(f"{title}: {text}" if title else text)
        elif stype == 'MEDIA':
            for media in section.get('media', []):
                if media.get('type') == 'PICTURE':
                    url = media.get('previewImageUrl') or media.get('fullImageUrl', '')
                    if url:
                        photos.append(url)

    result['description'] = "\n\n".join(descriptions)[:3000]
    result['photo_urls'] = photos
    result['total_photos'] = len(photos)
    return result


def _fetch_html_detail(expose: dict, parser_fn) -> dict:
    """Fetch HTML detail page and parse with platform-specific parser."""
    result = {'description': '', 'photo_urls': [], 'total_photos': 0}
    resp = requests.get(expose.get('url', ''), headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        return result
    soup = BeautifulSoup(resp.content, 'lxml')
    return parser_fn(soup)


def _parse_wggesucht(soup) -> dict:
    result = {'description': '', 'photo_urls': [], 'total_photos': 0}
    desc_el = soup.find('div', id='ad_description_text')
    if not desc_el:
        desc_el = soup.find('div', class_='freitext')
    if desc_el:
        result['description'] = desc_el.get_text(separator="\n", strip=True)[:2000]

    photos = []
    for img in soup.select('img.sp-image, div.wgg_gallery img'):
        src = img.get('data-src') or img.get('src', '')
        if src and src.startswith('http'):
            photos.append(src)
    result['photo_urls'] = list(dict.fromkeys(photos))
    result['total_photos'] = len(result['photo_urls'])
    return result


def _parse_kleinanzeigen(soup) -> dict:
    result = {'description': '', 'photo_urls': [], 'total_photos': 0}
    desc_el = soup.find('p', id='viewad-description-text')
    if desc_el:
        result['description'] = desc_el.get_text(separator="\n", strip=True)[:2000]

    photos = []
    for img in soup.select('#viewad-image img, .galleryimage img'):
        src = img.get('data-src') or img.get('src', '')
        if src and src.startswith('http'):
            photos.append(src)
    result['photo_urls'] = list(dict.fromkeys(photos))
    result['total_photos'] = len(result['photo_urls'])
    return result


def _build_listing_text(expose: dict, detail: dict) -> str:
    lines = [
        f"Title: {expose.get('title', 'N/A')}",
        f"Price: {expose.get('price', 'N/A')}",
        f"Size: {expose.get('size', 'N/A')}",
        f"Rooms: {expose.get('rooms', 'N/A')}",
        f"Address: {expose.get('address', 'N/A')}",
        f"Platform: {expose.get('crawler', 'N/A')}",
        f"Photos in listing: {detail.get('total_photos', 0)}",
    ]
    contact_name = detail.get('contact_name', '')
    if contact_name:
        lines.append(f"Contact/Agent: {contact_name}")
    if expose.get('from'):
        lines.append(f"Available from: {expose['from']}")
    if expose.get('to'):
        lines.append(f"Available until: {expose['to']}")
    if expose.get('durations'):
        lines.append(f"Commute: {expose['durations']}")

    description = detail.get('description', '')
    if description:
        lines.append(f"\nFull listing description:\n{description}")
    else:
        lines.append("\n(No description available)")

    return "\n".join(lines)


def score_listing(expose: dict, config) -> Optional[dict]:
    """Score a listing with Gemini. Returns {score, pros, cons, summary, message}."""
    api_key = config.auto_contact_gemini_api_key()
    if not api_key:
        return None

    user_profile = config.auto_contact_user_profile() or ""

    # Fetch detail page once — gets description + photo URLs
    detail = _fetch_detail_page(expose)
    listing_text = _build_listing_text(expose, detail)

    prompt = f"""You are evaluating a rental apartment listing in Berlin, Germany for a tenant:
{user_profile}

Listing:
{listing_text}

TASK 1: Rate 1-10 with brief pros, cons, one-sentence summary. Write in ENGLISH.
Scoring guidelines:
- HEAVILY reward well-maintained, renovated, modern apartments. Penalize old/unrenovated.
- Bonus points for separate bedrooms (not just "rooms"), dedicated office space, or extra rooms beyond the minimum.
- PENALIZE ground floor (Erdgeschoss/EG) apartments: -2 points. Ground floor = security and noise concerns.
- Check the "Photos in listing" count. 0 photos = -2 points. Don't judge by how many images are attached to this prompt — judge by the count in the listing data.
- Score heavily on value for money. A mediocre flat at max budget should score much lower than a great flat below budget.
- Consider commute times if provided. Under 15min transit = great, over 30min = bad.
- Furnished when tenant wants unfurnished = slight negative. Built-in kitchen (Einbauküche) is a plus.
- Penalize temporary/sublet listings if tenant wants long-term.
- Read the full listing description carefully — it contains critical details about condition, floor, amenities, and restrictions.

TASK 2: If score >= 7, write a contact message in German (formal "Sie").
Message rules:
- If a Contact/Agent name is given, address them by name (e.g. "Sehr geehrter Herr Arnst," or "Sehr geehrte Frau Weber,"). Use "Sehr geehrte Damen und Herren," only if no name is given. If name starts with "Privat von" or "Frau"/"Herr", extract the actual name.
- Start with the greeting, then the message body, then sign off with the tenant's names (e.g. "Mit freundlichen Grüßen, Mohamed & Valeriya Oun")
- 5-8 sentences in the body. Sound like a real human wrote this, not a template.
- DO NOT just parrot back the listing title or obvious facts. Instead, mention specific details that show you READ the description carefully — e.g. a specific renovation detail, a mentioned amenity, the neighborhood vibe, building character, a restriction you're fine with.
- Explain naturally why this apartment fits your family situation. Connect specific features to your life (baby needs a room, work-from-home needs an office, etc.)
- Weave in your reliability signals naturally (stable income, long-term Berlin residents, non-smokers) — don't list them like bullet points. Do NOT mention pets at all.
- Be warm and human. Vary sentence structure. Don't start every sentence with "Wir".
- No placeholder brackets.
- If score < 7, set message to null.

Respond with JSON: score, pros, cons, summary, message."""

    parts = [{"text": prompt}]

    try:
        resp = requests.post(
            f"{GEMINI_API_URL}?key={api_key}",
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": RESPONSE_SCHEMA,
                    "temperature": 0.5,
                },
            },
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error("Gemini API error (%d): %s", resp.status_code, resp.text[:500])
            return None

        data = resp.json()
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text")
        if not text:
            logger.error("Gemini empty response: %s", json.dumps(data)[:300])
            return None

        parsed = json.loads(text)
        if not isinstance(parsed.get("score"), (int, float)) or not isinstance(parsed.get("pros"), list):
            logger.error("Gemini bad schema: %s", text[:300])
            return None

        logger.info("Scored expose %s: %d/10 — %s",
                     expose.get('id'), parsed['score'], parsed.get('summary', ''))
        return parsed

    except Exception as e:
        logger.error("Gemini scoring failed for expose %s: %s", expose.get('id'), e)
        return None


def score_listings_parallel(exposes: list, config, max_workers: int = 10) -> list:
    """Score multiple listings in parallel. Returns exposes with gemini_* fields attached."""
    api_key = config.auto_contact_gemini_api_key()
    if not api_key:
        return exposes

    def _score_one(expose):
        result = score_listing(expose, config)
        if result:
            expose['gemini_score'] = result.get('score', 0)
            expose['gemini_pros'] = result.get('pros', [])
            expose['gemini_cons'] = result.get('cons', [])
            expose['gemini_summary'] = result.get('summary', '')
            expose['gemini_message'] = result.get('message')
        return expose

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_score_one, e): i for i, e in enumerate(exposes)}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error("Parallel scoring error: %s", e)

    return exposes
