"""Module with implementations of standard expose filters"""
from functools import reduce
import re
from abc import ABC, ABCMeta
from typing import List, Any
from flathunter.logging import logger

class AbstractFilter(ABC):
    """Abstract base class for filters"""

    def is_interesting(self, _expose):
        """Return True if an expose should be included in the output, False otherwise"""
        return True

class ExposeHelper:
    """Helper functions for extracting data from expose text"""

    @staticmethod
    def get_price(expose):
        """Extracts the price from a price text"""
        price_match = re.search(r'\d+([\.,]\d+)?', expose['price'])
        if price_match is None:
            return None
        price_str = price_match[0].replace(",", ".")
        return float(price_str)


    @staticmethod
    def get_size(expose):
        """Extracts the size from a size text"""
        size_match = re.search(r'\d+([\.,]\d+)?', expose['size'])
        if size_match is None:
            return None
        return float(size_match[0].replace(",", "."))

    @staticmethod
    def get_rooms(expose):
        """Extracts the number of rooms from a room text"""
        rooms_match = re.search(r'\d+([\.,]\d+)?', expose['rooms'])
        if rooms_match is None:
            return None
        return float(rooms_match[0].replace(",", "."))

class AlreadySeenFilter(AbstractFilter):
    """Filter exposes that have already been processed"""

    def __init__(self, id_watch):
        self.id_watch = id_watch

    def is_interesting(self, expose):
        if not self.id_watch.is_processed(expose['id']):
            self.id_watch.mark_processed(expose['id'])
            return True, ""
        return False, f"Expose {expose['id']} has already been processed."

class MaxPriceFilter(AbstractFilter):
    """Exclude exposes above a given price"""

    def __init__(self, max_price):
        self.max_price = max_price

    def is_interesting(self, expose):
        price = ExposeHelper.get_price(expose)
        if price is None:
            return True, ""
        if price <= self.max_price:
            return True, ""
        return False, f"Price {price} is above the max price {self.max_price}."

class MinPriceFilter(AbstractFilter):
    """Exclude exposes below a given price"""

    def __init__(self, min_price):
        self.min_price = min_price

    def is_interesting(self, expose):
        price = ExposeHelper.get_price(expose)
        if price is None:
            return True, ""
        if price >= self.min_price:
            return True, ""
        return False, f"Price {price} is below the min price {self.min_price}."

class MaxSizeFilter(AbstractFilter):
    """Exclude exposes above a given size"""

    def __init__(self, max_size):
        self.max_size = max_size

    def is_interesting(self, expose):
        size = ExposeHelper.get_size(expose)
        if size is None:
            return True, ""
        if size <= self.max_size:
            return True, ""
        return False, f"Size {size} is above the max size {self.max_size}."

class MinSizeFilter(AbstractFilter):
    """Exclude exposes below a given size"""

    def __init__(self, min_size):
        self.min_size = min_size

    def is_interesting(self, expose):
        size = ExposeHelper.get_size(expose)
        if size is None:
            return True, ""
        if size >= self.min_size:
            return True, ""
        return False, f"Size {size} is below the min size {self.min_size}."

class MaxRoomsFilter(AbstractFilter):
    """Exclude exposes above a given number of rooms"""

    def __init__(self, max_rooms):
        self.max_rooms = max_rooms

    def is_interesting(self, expose):
        rooms = ExposeHelper.get_rooms(expose)
        if rooms is None:
            return True, ""
        if rooms <= self.max_rooms:
            return True, ""
        return False, f"Rooms {rooms} is above the max rooms {self.max_rooms}."

class MinRoomsFilter(AbstractFilter):
    """Exclude exposes below a given number of rooms"""

    def __init__(self, min_rooms):
        self.min_rooms = min_rooms

    def is_interesting(self, expose):
        rooms = ExposeHelper.get_rooms(expose)
        if rooms is None:
            return True, ""
        if rooms >= self.min_rooms:
            return True, ""
        return False, f"Rooms {rooms} is below the min rooms {self.min_rooms}."

class TitleFilter(AbstractFilter):
    """Exclude exposes whose titles match the provided terms"""

    def __init__(self, filtered_titles):
        self.filtered_titles = filtered_titles

    def is_interesting(self, expose):
        combined_excludes = "(" + ")|(".join(self.filtered_titles) + ")"
        found_objects = re.search(combined_excludes, expose['title'], re.IGNORECASE)
        if not found_objects:
            return True, ""
        return False, f"Title '{expose['title']}' matches filtered titles."

class PPSFilter(AbstractFilter):
    """Exclude exposes above a given price per square"""

    def __init__(self, max_pps):
        self.max_pps = max_pps

    def is_interesting(self, expose):
        size = ExposeHelper.get_size(expose)
        price = ExposeHelper.get_price(expose)
        if size is None or price is None:
            return True, ""
        pps = price / size
        if pps <= self.max_pps:
            return True, ""
        return False, f"Price per square {pps} is above max price per square {self.max_pps}."

class FilterBuilder:
    """Construct a filter chain"""
    filters: List[AbstractFilter]

    def __init__(self):
        self.filters = []

    def _append_filter_if_not_empty(self, filter_class: ABCMeta, filter_config: Any):
        if not filter_config:
            return
        self.filters.append(filter_class(filter_config))

    def read_config(self, config):
        self._append_filter_if_not_empty(TitleFilter, config.excluded_titles())
        self._append_filter_if_not_empty(MinPriceFilter, config.min_price())
        self._append_filter_if_not_empty(MaxPriceFilter, config.max_price())
        self._append_filter_if_not_empty(MinSizeFilter, config.min_size())
        self._append_filter_if_not_empty(MaxSizeFilter, config.max_size())
        self._append_filter_if_not_empty(MinRoomsFilter, config.min_rooms())
        self._append_filter_if_not_empty(MaxRoomsFilter, config.max_rooms())
        self._append_filter_if_not_empty(PPSFilter, config.max_price_per_square())
        return self

    def filter_already_seen(self, id_watch):
        self.filters.append(AlreadySeenFilter(id_watch))
        return self

    def build(self):
        return Filter(self.filters)

class Filter:
    """Abstract filter object"""

    filters: List[AbstractFilter]

    def __init__(self, filters: List[AbstractFilter]):
        self.filters = filters

    def is_interesting_expose(self, expose):
        """Apply all filters to this expose"""
        explanations = []
        is_interesting = True

        for f in self.filters:
            result, explanation = f.is_interesting(expose)
            if not result:
                is_interesting = False
                explanations.append(explanation)

        return is_interesting, explanations

    def filter(self, exposes):
        """Apply all filters to every expose in the list"""
        filtered_exposes = []
        for expose in exposes:
            is_interesting, explanations = self.is_interesting_expose(expose)
            if is_interesting:
                filtered_exposes.append(expose)
            else:
                reasons = "\n - ".join(explanations)
                logger.debug("Excluding expose: %s\nReasons:\n - %s", expose['title'], reasons)

        return filtered_exposes

    @staticmethod
    def builder():
        """Return a new filter builder"""
        return FilterBuilder()