"""Sensors: numeric / string tags."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RockwellEntity, entities_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(entities_for(entry, "sensor", RockwellSensor))


class RockwellSensor(RockwellEntity, SensorEntity):
    def __init__(self, coordinator, entry, cfg) -> None:
        super().__init__(coordinator, entry, cfg)
        self._attr_native_unit_of_measurement = cfg.unit
        self._attr_suggested_display_precision = cfg.precision
        if cfg.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(cfg.device_class)
            except ValueError:
                _LOGGER.warning("%s: unknown sensor device_class '%s' ignored", cfg.tag, cfg.device_class)
        if cfg.state_class:
            try:
                self._attr_state_class = SensorStateClass(cfg.state_class)
            except ValueError:
                _LOGGER.warning("%s: unknown state_class '%s' ignored", cfg.tag, cfg.state_class)

    @property
    def native_value(self) -> Any:
        raw = self.raw
        if isinstance(raw, (dict, list, tuple)):
            return None  # structures/arrays are exposed as an attribute instead
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, str):
            return raw[:255]
        return self.cfg.to_ha(raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(self._attr_extra_state_attributes)
        raw = self.raw
        if isinstance(raw, (dict, list, tuple)):
            attrs["value"] = raw
        return attrs
