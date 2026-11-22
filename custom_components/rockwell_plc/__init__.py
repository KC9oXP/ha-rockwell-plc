"""Rockwell / Allen-Bradley PLC integration (Logix 5000 and SLC/MicroLogix over EtherNet/IP)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_TAG,
    ATTR_VALUE,
    CONF_ALLOW_SERVICE_WRITES,
    CONF_PATH,
    CONF_PLC_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_TAGS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_READ_TAG,
    SERVICE_WRITE_TAG,
)
from .coordinator import RockwellCoordinator
from .plc import PLCClient
from .tags import TagConfig, TagConfigError, parse_tags

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class RockwellData:
    client: PLCClient
    coordinator: RockwellCoordinator
    tags: list[TagConfig]


type RockwellConfigEntry = ConfigEntry[RockwellData]

WRITE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_TAG): cv.string,
        vol.Required(ATTR_VALUE): vol.Any(bool, int, float, str, list),
    }
)
READ_SCHEMA = vol.Schema(
    {vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string, vol.Required(ATTR_TAG): cv.string}
)


def _loaded_entry(hass: HomeAssistant, entry_id: str) -> RockwellConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"{entry_id} is not a {DOMAIN} config entry")
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(f"PLC '{entry.title}' is not loaded")
    return entry


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services (once, not per PLC)."""

    async def write_tag(call: ServiceCall) -> None:
        entry = _loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        if not entry.options.get(CONF_ALLOW_SERVICE_WRITES, False):
            raise ServiceValidationError(
                f"Service writes are disabled for '{entry.title}'. "
                "Enable 'Allow write_tag service' in the integration options."
            )
        await entry.runtime_data.coordinator.async_write(call.data[ATTR_TAG], call.data[ATTR_VALUE])

    async def read_tag(call: ServiceCall) -> ServiceResponse:
        entry = _loaded_entry(hass, call.data[ATTR_CONFIG_ENTRY_ID])
        result = await entry.runtime_data.coordinator.async_read_one(call.data[ATTR_TAG])
        return {"tag": call.data[ATTR_TAG], "value": result.value, "error": result.error}

    hass.services.async_register(DOMAIN, SERVICE_WRITE_TAG, write_tag, schema=WRITE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_READ_TAG, read_tag, schema=READ_SCHEMA, supports_response=SupportsResponse.ONLY
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RockwellConfigEntry) -> bool:
    try:
        tags = parse_tags(entry.options.get(CONF_TAGS, ""))
    except TagConfigError as err:
        raise ConfigEntryError(f"Invalid tag list: {err}") from err

    client = PLCClient(entry.data[CONF_PLC_TYPE], entry.data[CONF_PATH])
    # Buttons are write-only; everything else gets polled.
    addresses = list(dict.fromkeys(t.tag for t in tags if t.platform != "button"))
    coordinator = RockwellCoordinator(
        hass,
        entry,
        client,
        addresses,
        float(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await hass.async_add_executor_job(client.close)
        raise

    entry.runtime_data = RockwellData(client, coordinator, tags)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: RockwellConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RockwellConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded
