"""Provides logger"""
import logging
import os
from pprint import pformat


class LoggerHandler(logging.StreamHandler):
    """Formats logs with colored output"""

    _CYELLOW = '\033[93m' if os.name == 'posix' else ''
    _CBLUE = '\033[94m' if os.name == 'posix' else ''
    _COFF = '\033[0m' if os.name == 'posix' else ''
    _FORMAT = '[' + _CBLUE + '%(asctime)s' + _COFF + \
              '|' + _CBLUE + '%(filename)-24s' + _COFF + \
              '|' + _CYELLOW + '%(levelname)-8s' + _COFF + \
              ']: %(message)s'
    _DATE_FORMAT = '%Y/%m/%d %H:%M:%S'

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(
            fmt=self._FORMAT,
            datefmt=self._DATE_FORMAT
        ))


# Setup Flathunter logger
logger_handler = LoggerHandler()
logging.basicConfig(level=logging.INFO, handlers=[logger_handler])
logger = logging.getLogger('flathunt')

# Setup "requests" module's logger
logging.getLogger("requests").setLevel(logging.WARNING)

def configure_logging(config):
    """Setup the logging classes based on verbose config flag"""
    if config.verbose_logging():
        logger.setLevel(logging.DEBUG)
    logger.debug("Settings from config: %s", pformat(config))
