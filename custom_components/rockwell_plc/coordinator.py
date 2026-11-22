"""Polling coordinator for one PLC."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .plc import PLCClient, PLCError, TagValue

_LOGGER = logging.getLogger(__name__)


class RockwellCoordinator(DataUpdateCoordinator[dict[str, TagValue]]):
    """Reads every configured tag once per scan interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PLCClient,
        addresses: list[str],
        scan_interval: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.addresses = addresses
        self._logged_tag_errors: set[str] = set()

    async def _async_update_data(self) -> dict[str, TagValue]:
        try:
            data = await self.hass.async_add_executor_job(self.client.read, self.addresses)
        except PLCError as err:
            raise UpdateFailed(str(err)) from err
        for tag, val in data.items():
            if val.error and tag not in self._logged_tag_errors:
                _LOGGER.warning("%s: tag %s read error: %s", self.name, tag, val.error)
                self._logged_tag_errors.add(tag)
            elif not val.error:
                self._logged_tag_errors.discard(tag)
        return data

    def last_raw(self, tag: str) -> Any:
        if not self.data or tag not in self.data:
            return None
        return self.data[tag].value

    async def async_write(self, tag: str, value: Any, refresh: bool = True) -> None:
        try:
            await self.hass.async_add_executor_job(self.client.write, tag, value)
        except PLCError as err:
            raise HomeAssistantError(str(err)) from err
        if refresh:
            await self.async_request_refresh()

    async def async_read_one(self, tag: str) -> TagValue:
        try:
            data = await self.hass.async_add_executor_job(self.client.read, [tag])
        except PLCError as err:
            raise HomeAssistantError(str(err)) from err
        return data[tag]
