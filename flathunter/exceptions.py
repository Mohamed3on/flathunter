"""User-defined exception classes"""


class BotBlockedException(Exception):
    """Raised when bot tries to send a message to a user that has blocked the bot"""


class UserDeactivatedException(Exception):
    """Raised when bot tries to send a message to a deactivated user"""


class PersistenceException(Exception):
    """Problem with backend storage"""


class ConfigException(Exception):
    """Problem with the configuration"""
