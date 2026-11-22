"""Binary sensors: BOOL tags and bits."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RockwellEntity, entities_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(entities_for(entry, "binary_sensor", RockwellBinarySensor))


class RockwellBinarySensor(RockwellEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, cfg) -> None:
        super().__init__(coordinator, entry, cfg)
        if cfg.device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(cfg.device_class)
            except ValueError:
                _LOGGER.warning("%s: unknown binary_sensor device_class '%s' ignored", cfg.tag, cfg.device_class)

    @property
    def is_on(self) -> bool | None:
        raw = self.raw
        if raw is None:
            return None
        return bool(raw) != self.cfg.invert
