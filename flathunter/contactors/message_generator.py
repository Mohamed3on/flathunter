"""Score listings and generate contact messages using Gemini"""
import json
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

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


def _build_listing_text(expose: dict) -> str:
    lines = [
        f"Title: {expose.get('title', 'N/A')}",
        f"Price: {expose.get('price', 'N/A')}",
        f"Size: {expose.get('size', 'N/A')}",
        f"Rooms: {expose.get('rooms', 'N/A')}",
        f"Address: {expose.get('address', 'N/A')}",
        f"Platform: {expose.get('crawler', 'N/A')}",
        f"Photos in listing: {expose.get('detail_total_photos', 0)}",
    ]
    contact_name = expose.get('detail_contact_name', '')
    if contact_name:
        lines.append(f"Contact/Agent: {contact_name}")
    if expose.get('from'):
        lines.append(f"Available from: {expose['from']}")
    if expose.get('to'):
        lines.append(f"Available until: {expose['to']}")
    if expose.get('durations'):
        lines.append(f"Commute: {expose['durations']}")

    description = expose.get('detail_description', '')
    if description:
        lines.append(f"\nFull listing description:\n{description}")
    else:
        lines.append("\n(No description available)")

    return "\n".join(lines)


def score_listing(expose: dict, config) -> Optional[dict]:
    """Score a listing with Gemini. Returns {score, pros, cons, summary, message}.
    Expects expose to be enriched with detail_* fields by CrawlExposeDetails processor."""
    api_key = config.auto_contact_gemini_api_key()
    if not api_key:
        return None

    user_profile = config.auto_contact_user_profile() or ""
    listing_text = _build_listing_text(expose)

    prompt = f"""You are evaluating a rental apartment listing in Berlin, Germany for a tenant:
{user_profile}

Listing:
{listing_text}

TASK 1: Rate 1-10 with brief pros, cons, one-sentence summary. Write in ENGLISH.
Scoring guidelines:
- HEAVILY reward well-maintained, renovated, modern apartments. Penalize old/unrenovated.
- Bonus points for separate bedrooms (not just "rooms"), dedicated office space, or extra rooms beyond the minimum.
- PENALIZE ground floor (Erdgeschoss/EG) apartments: -2 points. Ground floor = security and noise concerns.
- Score heavily on value for money. A mediocre flat at max budget should score much lower than a great flat below budget.
- COMMUTE IS CRITICAL: If ANY transport mode takes > 33 mins, -1 point. If ANY mode is under 12 mins, +1 point. ✅ = within configured limit, ❌ = exceeds limit.
- Furnished when tenant wants unfurnished = slight negative. Built-in kitchen (Einbauküche) is a plus.
- Longer lease periods are a PLUS, not a negative. The tenant wants a long-term home.
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


def score_listings_parallel(exposes: list, config, max_workers: int = 10) -> None:
    """Score multiple listings in parallel. Mutates each expose dict in-place,
    adding gemini_score, gemini_pros, gemini_cons, gemini_summary, gemini_message."""
    api_key = config.auto_contact_gemini_api_key()
    if not api_key:
        return

    def _score_one(expose):
        result = score_listing(expose, config)
        if result:
            expose['gemini_score'] = result.get('score', 0)
            expose['gemini_pros'] = result.get('pros', [])
            expose['gemini_cons'] = result.get('cons', [])
            expose['gemini_summary'] = result.get('summary', '')
            expose['gemini_message'] = result.get('message')

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_score_one, e) for e in exposes]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logger.error("Parallel scoring error: %s", e)
