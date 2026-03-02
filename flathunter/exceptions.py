"""Some user-defined exception classes"""

class ValueException(Exception):
    """A generic exception class"""
    def __init__(self, message):
        self.value = str(message)
        Exception.__init__(self, self.value)

    def __str__(self):
        return self.value

class BotBlockedException(ValueException):
    """
    A small class that defines a Bot Blocked Exception.
    """

class UserDeactivatedException(ValueException):
    """
    A small class that defines a UserDeactivated Exception.
    """

class PersistenceException(ValueException):
    """
    Exception indicating a problem with backend storage
    """

class ConfigException(ValueException):
    """
    Exception indicating a problem with the configuration
    """
