"""Wrap configuration options as an object"""
import os
from typing import Optional, Dict, Any, List, Protocol

import yaml
from dotenv import load_dotenv

from flathunter.crawler.kleinanzeigen import Kleinanzeigen
from flathunter.crawler.immobilienscout import Immobilienscout
from flathunter.crawler.wggesucht import WgGesucht
from flathunter.logging import logger
from flathunter.exceptions import ConfigException

load_dotenv()

class Readenv(Protocol):
    """Type information for the read_env callback"""
    @staticmethod
    def __call__() -> Optional[str]: ...

def _read_env(key: str, fallback: Optional[str] = None) -> Readenv:
    """ read the given key from environment"""
    return lambda: os.environ.get(key, fallback)

def _to_bool(value: Any) -> bool:
    """Cast config parameters to booleans"""
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in ("true", "1", "on", "yes", "y"):
        return True
    if value in ("false", "0", "off", "no", "n"):
        return False
    error_msg = f"Cannot convert config parameter '{value}' to boolean"
    logger.error(error_msg)
    raise ValueError(error_msg)

class Env:
    """Reads data from the environment"""

    FLATHUNTER_IS24_COOKIE = _read_env("FLATHUNTER_IS24_COOKIE")

    # Generic Config
    FLATHUNTER_TARGET_URLS = _read_env("FLATHUNTER_TARGET_URLS")
    FLATHUNTER_GOOGLE_CLOUD_PROJECT_ID = _read_env(
        "FLATHUNTER_GOOGLE_CLOUD_PROJECT_ID")
    FLATHUNTER_VERBOSE_LOG = _read_env("FLATHUNTER_VERBOSE_LOG")
    FLATHUNTER_LOOP_PERIOD_SECONDS = _read_env(
        "FLATHUNTER_LOOP_PERIOD_SECONDS")
    FLATHUNTER_RANDOM_JITTER_ENABLED = _read_env("FLATHUNTER_RANDOM_JITTER_ENABLED")
    FLATHUNTER_LOOP_PAUSE_FROM = _read_env("FLATHUNTER_LOOP_PAUSE_FROM")
    FLATHUNTER_LOOP_PAUSE_TILL = _read_env("FLATHUNTER_LOOP_PAUSE_TILL")
    FLATHUNTER_MESSAGE_FORMAT = _read_env("FLATHUNTER_MESSAGE_FORMAT")

    # Notification setup
    FLATHUNTER_NOTIFIERS = _read_env("FLATHUNTER_NOTIFIERS")
    FLATHUNTER_TELEGRAM_BOT_TOKEN = _read_env("FLATHUNTER_TELEGRAM_BOT_TOKEN")
    FLATHUNTER_TELEGRAM_BOT_NOTIFY_WITH_IMAGES = \
        _read_env("FLATHUNTER_TELEGRAM_BOT_NOTIFY_WITH_IMAGES")
    FLATHUNTER_TELEGRAM_RECEIVER_IDS = _read_env(
        "FLATHUNTER_TELEGRAM_RECEIVER_IDS")
    FLATHUNTER_APPRISE_NOTIFY_WITH_IMAGES = _read_env(
        "FLATHUNTER_APPRISE_NOTIFY_WITH_IMAGES")
    FLATHUNTER_APPRISE_IMAGE_LIMIT = _read_env(
        "FLATHUNTER_APPRISE_IMAGE_LIMIT")

    # Filters
    FLATHUNTER_FILTER_EXCLUDED_TITLES = _read_env(
        "FLATHUNTER_FILTER_EXCLUDED_TITLES")
    FLATHUNTER_FILTER_MIN_PRICE = _read_env("FLATHUNTER_FILTER_MIN_PRICE")
    FLATHUNTER_FILTER_MAX_PRICE = _read_env("FLATHUNTER_FILTER_MAX_PRICE")
    FLATHUNTER_FILTER_MIN_SIZE = _read_env("FLATHUNTER_FILTER_MIN_SIZE")
    FLATHUNTER_FILTER_MAX_SIZE = _read_env("FLATHUNTER_FILTER_MAX_SIZE")
    FLATHUNTER_FILTER_MIN_ROOMS = _read_env("FLATHUNTER_FILTER_MIN_ROOMS")
    FLATHUNTER_FILTER_MAX_ROOMS = _read_env("FLATHUNTER_FILTER_MAX_ROOMS")


class YamlConfig:
    """Generic config object constructed from nested dictionaries"""

    DEFAULT_MESSAGE_FORMAT = """{title}
Zimmer: {rooms}
Größe: {size}
Preis: {price}

{url}"""

    def __init__(self, config=None):
        if config is None:
            config = {}
        self.config = config
        self.__searchers__ = []

    def __iter__(self):
        """Emulate dictionary"""
        return self.config.__iter__()

    def __getitem__(self, value):
        """Emulate dictionary"""
        return self.config[value]

    def init_searchers(self):
        """Initialize search plugins"""
        self.__searchers__ = [
            Immobilienscout(self),
            WgGesucht(self),
            Kleinanzeigen(self),
        ]

    def get(self, key, value=None):
        """Emulate dictionary"""
        return self.config.get(key, value)

    def _read_yaml_path(self, path, default_value):
        """Resolve a dotted variable path in nested dictionaries"""
        config = self.config
        parts = path.split('.')
        while len(parts) > 1 and config is not None:
            config = config.get(parts[0], {})
            parts = parts[1:]
        if config is None:
            return default_value
        res = config.get(parts[0], default_value)
        if res is None:
            return default_value
        return res

    def set_searchers(self, searchers):
        """Update the active search plugins"""
        self.__searchers__ = searchers

    def searchers(self):
        """Get the list of search plugins"""
        return self.__searchers__

    def target_urls(self) -> List[str]:
        """List of target URLs for crawling"""
        return self._read_yaml_path('urls', [])

    def verbose_logging(self):
        """Return true if logging should be verbose"""
        return self._read_yaml_path('verbose', None) is not None

    def loop_is_active(self):
        """Return true if flathunter should be crawling in a loop"""
        return self._read_yaml_path('loop.active', False)

    def loop_period_seconds(self):
        """Number of seconds to wait between crawls when looping"""
        return self._read_yaml_path('loop.sleeping_time', 60 * 10)

    def random_jitter_enabled(self):
        """Whether a random delay should be added to loop sleeping time, defaults to true"""
        return self._read_yaml_path('loop.random_jitter', True)

    def loop_pause_from(self):
        """Start time of loop pause"""
        return self._read_yaml_path('loop.pause.from', "00:00")

    def loop_pause_till(self):
        """End time of loop pause"""
        return self._read_yaml_path('loop.pause.till', "00:00")

    def google_cloud_project_id(self):
        """Google Cloud project ID for App Engine / Cloud Run deployments"""
        return self._read_yaml_path('google_cloud_project_id', None)

    def message_format(self):
        """Format of the message to send in user notifications"""
        config_format = self._read_yaml_path('message', None)
        if config_format is not None:
            return config_format
        return self.DEFAULT_MESSAGE_FORMAT

    def telegram_preferred_max_pps(self):
        """Preferred maximum price per square meter"""
        return self._read_yaml_path("telegram.preferred_max_pps", None)

    def notifiers(self) -> List[str]:
        """List of currently-active notifiers"""
        return self._read_yaml_path('notifiers', [])

    def telegram_bot_token(self) -> Optional[str]:
        """API Token to authenticate to the Telegram bot"""
        return self._read_yaml_path('telegram.bot_token', None)

    def telegram_notify_with_images(self) -> bool:
        """True if images should be sent along with notifications"""
        flag = str(self._read_yaml_path(
            "telegram.notify_with_images", 'false'))
        return flag.lower() == 'true'

    def telegram_receiver_ids(self):
        """Static list of receiver IDs for notification messages"""
        return self._read_yaml_path('telegram.receiver_ids', [])

    def apprise_urls(self) -> List[str]:
        """Notification URLs for Apprise"""
        return self._read_yaml_path('apprise', [])

    def apprise_notify_with_images(self) -> bool:
        """True if images should be sent along with notifications"""
        flag = str(self._read_yaml_path(
            "apprise_notify_with_images", 'false'))
        return flag.lower() == 'true'

    def apprise_image_limit(self) -> Optional[int]:
        """How many images should be sent along with Apprise notifications"""
        return self._read_yaml_path('apprise_image_limit', None)

    def use_proxy(self):
        """Check if proxy is configured"""
        return "use_proxy_list" in self.config and self.config["use_proxy_list"]

    def set_keys(self, dict_keys: Dict[str, Any]):
        """Update the config keys based on the content of the dictionary passed"""
        self.config.update(dict_keys)

    def _get_filter_config(self, key: str) -> Optional[Any]:
        return (self.config.get("filters", {}) or {}).get(key, None)

    def excluded_titles(self):
        """Return the configured list of titles to exclude"""
        if "excluded_titles" in self.config:
            return self.config["excluded_titles"]
        return self._get_filter_config("excluded_titles") or []

    def min_price(self):
        """Return the configured minimum price"""
        return self._get_filter_config("min_price")

    def max_price(self):
        """Return the configured maximum price"""
        return self._get_filter_config("max_price")

    def min_size(self):
        """Return the configured minimum size"""
        return self._get_filter_config("min_size")

    def max_size(self):
        """Return the configured maximum size"""
        return self._get_filter_config("max_size")

    def min_rooms(self):
        """Return the configured minimum number of rooms"""
        return self._get_filter_config("min_rooms")

    def max_rooms(self):
        """Return the configured maximum number of rooms"""
        return self._get_filter_config("max_rooms")

    def immoscout_cookie(self):
        """Return the precalculated immoscout cookie"""
        return self._read_yaml_path('immoscout_cookie', None)

    def immoscout_session_cookies(self):
        """Return the full ImmoScout session cookie string for Selenium auth"""
        return self._read_yaml_path('immoscout_session_cookies', None)

    def twocaptcha_api_key(self):
        """API key for 2captcha service"""
        return self._read_yaml_path('twocaptcha_api_key', None) \
            or self._read_yaml_path('captcha.2captcha.api_key', None)

    def auto_contact_enabled(self):
        """Return true if auto-contact is enabled"""
        return self._read_yaml_path('auto_contact.enabled', False)

    def auto_contact_dry_run(self):
        """Return true if auto-contact is in dry-run mode"""
        return self._read_yaml_path('auto_contact.dry_run', True)

    def auto_contact_delay_min(self):
        """Minimum delay between auto-contact messages in seconds"""
        return self._read_yaml_path('auto_contact.delay_min', 30)

    def auto_contact_delay_max(self):
        """Maximum delay between auto-contact messages in seconds"""
        return self._read_yaml_path('auto_contact.delay_max', 60)

    def auto_contact_gemini_api_key(self):
        """Gemini API key for generating tailored messages"""
        return self._read_yaml_path('auto_contact.gemini_api_key', None)

    def auto_contact_gemini_prompt(self):
        """System prompt for Gemini message generation"""
        return self._read_yaml_path('auto_contact.gemini_prompt', None)

    def auto_contact_user_profile(self):
        """User profile for Gemini to personalize messages"""
        return self._read_yaml_path('auto_contact.user_profile', None)

    def auto_contact_wg_gesucht(self):
        """WG-Gesucht credentials for auto-contact"""
        return self._read_yaml_path('auto_contact.wg_gesucht', {})

    def auto_contact_kleinanzeigen(self):
        """Kleinanzeigen credentials for auto-contact"""
        return self._read_yaml_path('auto_contact.kleinanzeigen', {})

    def auto_contact_immoscout(self):
        """ImmoScout24 contact details for auto-contact"""
        return self._read_yaml_path('auto_contact.immoscout', {})


class Config(YamlConfig):
    """Flathunter configuration built from a file, supporting environment variable overrides"""

    def __init__(self, filename=None):
        if filename is None and Env.FLATHUNTER_TARGET_URLS() is None:
            raise ConfigException(
                "Config file location must be specified, or FLATHUNTER_TARGET_URLS must be set")
        if filename is not None:
            logger.info("Using config path %s", filename)
            if not os.path.exists(filename):
                raise ConfigException("No config file found at location %s")
            with open(filename, encoding="utf-8") as file:
                config = yaml.safe_load(file)
        else:
            config = {}
        super().__init__(config)

    def target_urls(self):
        env_urls = Env.FLATHUNTER_TARGET_URLS()
        if env_urls is not None:
            return env_urls.split(';')
        return super().target_urls()

    def verbose_logging(self):
        if Env.FLATHUNTER_VERBOSE_LOG() is not None:
            return True
        return super().verbose_logging()

    def loop_is_active(self):
        if Env.FLATHUNTER_LOOP_PERIOD_SECONDS() is not None:
            return True
        return super().loop_is_active()

    def loop_period_seconds(self):
        env_seconds = Env.FLATHUNTER_LOOP_PERIOD_SECONDS()
        if env_seconds is not None:
            return int(env_seconds)
        return super().loop_period_seconds()

    def random_jitter_enabled(self):
        env_jitter = Env.FLATHUNTER_RANDOM_JITTER_ENABLED()
        if env_jitter is not None:
            return _to_bool(env_jitter)
        return _to_bool(super().random_jitter_enabled())

    def loop_pause_from(self):
        env_pause = Env.FLATHUNTER_LOOP_PAUSE_FROM()
        if env_pause is not None:
            return str(env_pause)
        return super().loop_pause_from()

    def loop_pause_till(self):
        env_until = Env.FLATHUNTER_LOOP_PAUSE_TILL()
        if env_until is not None:
            return str(env_until)
        return super().loop_pause_till()

    def google_cloud_project_id(self):
        return Env.FLATHUNTER_GOOGLE_CLOUD_PROJECT_ID() or super().google_cloud_project_id()

    def message_format(self):
        env_message_format = Env.FLATHUNTER_MESSAGE_FORMAT()
        if env_message_format is not None:
            return '\n'.join(env_message_format.split('#CR#'))
        return super().message_format()

    def notifiers(self):
        env_notifiers = Env.FLATHUNTER_NOTIFIERS()
        if env_notifiers is not None:
            return env_notifiers.split(",")
        return super().notifiers()

    def telegram_bot_token(self) -> Optional[str]:
        return Env.FLATHUNTER_TELEGRAM_BOT_TOKEN() or super().telegram_bot_token()

    def telegram_notify_with_images(self) -> bool:
        env_bot_images = Env.FLATHUNTER_TELEGRAM_BOT_NOTIFY_WITH_IMAGES()
        if env_bot_images is not None:
            return str(env_bot_images) == 'true'
        return super().telegram_notify_with_images()

    def telegram_receiver_ids(self):
        env_receiver_ids = Env.FLATHUNTER_TELEGRAM_RECEIVER_IDS()
        if env_receiver_ids is not None:
            return [int(x) for x in env_receiver_ids.split(",")]
        return super().telegram_receiver_ids()

    def apprise_notify_with_images(self) -> bool:
        if Env.FLATHUNTER_APPRISE_NOTIFY_WITH_IMAGES() is not None:
            return str(Env.FLATHUNTER_APPRISE_NOTIFY_WITH_IMAGES()) == 'true'
        return super().apprise_notify_with_images()

    def apprise_image_limit(self) -> Optional[int]:
        env_limit = Env.FLATHUNTER_APPRISE_IMAGE_LIMIT()
        if env_limit is not None:
            return int(env_limit)
        return super().apprise_image_limit()

    def excluded_titles(self):
        env_filter = Env.FLATHUNTER_FILTER_EXCLUDED_TITLES()
        if env_filter is not None:
            return env_filter.split(";")
        return super().excluded_titles()

    def min_price(self):
        env_price = Env.FLATHUNTER_FILTER_MIN_PRICE()
        if env_price is not None:
            return int(env_price)
        return super().min_price()

    def max_price(self):
        env_price = Env.FLATHUNTER_FILTER_MAX_PRICE()
        if env_price is not None:
            return int(env_price)
        return super().max_price()

    def min_size(self):
        env_size = Env.FLATHUNTER_FILTER_MIN_SIZE()
        if env_size is not None:
            return int(env_size)
        return super().min_size()

    def max_size(self):
        env_size = Env.FLATHUNTER_FILTER_MAX_SIZE()
        if env_size is not None:
            return int(env_size)
        return super().max_size()

    def min_rooms(self):
        env_rooms = Env.FLATHUNTER_FILTER_MIN_ROOMS()
        if env_rooms is not None:
            return int(env_rooms)
        return super().min_rooms()

    def max_rooms(self):
        env_rooms = Env.FLATHUNTER_FILTER_MAX_ROOMS()
        if env_rooms is not None:
            return int(env_rooms)
        return super().max_rooms()

    def immoscout_cookie(self):
        return Env.FLATHUNTER_IS24_COOKIE() or super().immoscout_cookie()
