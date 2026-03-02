"""Auto-contact landlords on matching listings"""
from abc import ABC, abstractmethod


class AbstractContactor(ABC):
    """Base class for platform-specific contactors"""

    @abstractmethod
    def login(self) -> bool:
        """Authenticate with the platform. Returns True on success."""

    @abstractmethod
    def send_message(self, expose: dict, message: str) -> bool:
        """Send a message to the landlord for the given expose. Returns True on success."""
