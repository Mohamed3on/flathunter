"""Shared utility functions"""
import re


def parse_german_price(text: str) -> float | None:
    """'1.967,80 €' -> 1967.8"""
    m = re.search(r'[\d.]+,\d+', text)
    if not m:
        return None
    return float(m.group().replace('.', '').replace(',', '.'))
