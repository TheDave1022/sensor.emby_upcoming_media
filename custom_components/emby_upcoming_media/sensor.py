"""
Home Assistant component to feed the Upcoming Media Lovelace card with
Emby Latest Media.

https://github.com/gcorgnet/sensor.emby_upcoming_media

https://github.com/custom-cards/upcoming-media-card

"""
import logging
import json
import time
import re
import requests
from datetime import date, datetime
from datetime import timedelta
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components import sensor
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.helpers.entity import Entity

from .client import EmbyClient

__version__ = "0.0.1"

DOMAIN = "emby_upcoming_media"
DOMAIN_DATA = f"{DOMAIN}_data"
ATTRIBUTION = "Data is provided by Emby."

# Configuration
CONF_SENSOR = "sensor"
CONF_ENABLED = "enabled"
CONF_NAME = "name"
CONF_INCLUDE = "include"
CONF_MAX = "max"
CONF_USER_ID = "user_id"

CATEGORY_NAME = "CategoryName"
CATEGORY_ID = "CategoryId"

SCAN_INTERVAL_SECONDS = 3600  # Scan once per hour

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_API_KEY): cv.string,
        vol.Optional(CONF_USER_ID): cv.string,
        vol.Optional(CONF_HOST, default="localhost"): cv.string,
        vol.Optional(CONF_PORT, default=8096): cv.port,
        vol.Optional(CONF_SSL, default=False): cv.boolean,
        vol.Optional(CONF_INCLUDE, default=[]): vol.All(cv.ensure_list),
        vol.Optional(CONF_MAX, default=5): cv.Number,
    }
)


def setup_platform(hass, config, add_devices, discovery_info=None):

    # Create DATA dict
    hass.data[DOMAIN_DATA] = {}

    # Get "global" configuration.
    api_key = config.get(CONF_API_KEY)
    host = config.get(CONF_HOST)
    ssl = config.get(CONF_SSL)
    port = config.get(CONF_PORT)
    max_items = config.get(CONF_MAX)
    user_id = config.get(CONF_USER_ID)
    include = config.get(CONF_INCLUDE)

    # Configure the client.
    client = EmbyClient(host, api_key, ssl, port, max_items, user_id)
    hass.data[DOMAIN_DATA]["client"] = client

    categories = client.get_view_categories()

    if include != []:
        categories = filter(lambda el: el["Name"] in include, categories)

    mapped = map(
        lambda cat: EmbyUpcomingMediaSensor(
            hass, {**config, CATEGORY_NAME: cat["Name"], CATEGORY_ID: cat["Id"]}
        ),
        categories,
    )

    add_devices(mapped, True)


SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)


class EmbyUpcomingMediaSensor(Entity):
    def __init__(self, hass, conf):
        self._client = hass.data[DOMAIN_DATA]["client"]
        self._state = None
        self.data = []
        self.category_name = conf.get(CATEGORY_NAME)
        self.category_id = conf.get(CATEGORY_ID)
        self.friendly_name = "Emby Upcoming Media " + self.category_name
        self.entity_id = sensor.ENTITY_ID_FORMAT.format(
            "emby_latest_"
            + re.sub(
                "\W+", "_", self.category_name
            ).lower()  # remove special characters
        )

    @property
    def name(self):
        return "Latetst {0} on Emby".format(self.category_name)

    @property
    def state(self):
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes."""

        attributes = {}
        default = {}
        card_json = []
        default["title_default"] = "$title"
        default["line1_default"] = "$number - $studio"
        default["line2_default"] = "$aired"
        default["line3_default"] = "$episode"
        default["line4_default"] = "$rating - $runtime"

        default["icon"] = "mdi:arrow-down-bold"
        card_json.append(default)

        # for show in self.data[self._category_id]:
        for show in self.data:
            card_item = {}
            card_item["title"] = show["Name"]

            card_item["episode"] = show.get("OfficialRating", "")
            card_item["officialrating"] = show.get("OfficialRating", "")

            card_item["airdate"] = show.get("PremiereDate", datetime.now().isoformat())

            timeobject = timedelta(microseconds=show["RunTimeTicks"] / 10)

            card_item["runtime"] = timeobject.total_seconds() / 60
            if "ParentIndexNumber" and "IndexNumber" in show:
                card_item["number"] = "S{:02d}E{:02d}".format(
                    show["ParentIndexNumber"], show["IndexNumber"]
                )
            else:
                card_item["number"] = show.get("ProductionYear", "")

            card_item["poster"] = self.hass.data[DOMAIN_DATA]["client"].get_image_url(
                show["Id"], show["ImageTags"]["Primary"]
            )

            card_item["rating"] = "%s %s" % (
                "\u2605",  # Star character
                show.get("CommunityRating", ""),
            )

            card_json.append(card_item)

        attributes["data"] = json.dumps(card_json)
        attributes["attribution"] = ATTRIBUTION
        return attributes

    def update(self):
        data = self._client.get_data(self.category_id)

        if data is not None:
            self._state = "Online"
            self.data = data
        else:
            self._state = "error"
