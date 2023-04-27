""" Startup file for Google Cloud deployment or local webserver"""
import os

from flathunter.argument_parser import parse
from flathunter.googlecloud_idmaintainer import GoogleCloudIdMaintainer
from flathunter.web_hunter import WebHunter
from flathunter.config import Config
from flathunter.logging import configure_logging

# load config
args = parse()
config_handle = args.config
if config_handle is not None:
    config = Config(config_handle.name)
else:
    config = Config()

# Load the driver manager from local cache (if chrome_driver_install.py has been run
os.environ['WDM_LOCAL'] = '1'
# Use Google Cloud DB if we run on the cloud
id_watch = GoogleCloudIdMaintainer(config)

configure_logging(config)

# initialize search plugins for config
config.init_searchers()

hunter = WebHunter(config, id_watch)

hunter.hunt_flats()
