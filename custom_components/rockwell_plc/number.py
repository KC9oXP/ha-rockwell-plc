"""Numbers: writable numeric tags (setpoints). Only created when writes are enabled."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RockwellEntity, entities_for
from .tags import coerce_for_write


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(entities_for(entry, "number", RockwellNumber))


class RockwellNumber(RockwellEntity, NumberEntity):
    def __init__(self, coordinator, entry, cfg) -> None:
        super().__init__(coordinator, entry, cfg)
        self._attr_native_min_value = cfg.min
        self._attr_native_max_value = cfg.max
        self._attr_native_step = cfg.step
        self._attr_native_unit_of_measurement = cfg.unit
        self._attr_mode = NumberMode(cfg.mode)

    @property
    def native_value(self) -> float | None:
        raw = self.raw
        if isinstance(raw, bool):
            return float(raw)
        if not isinstance(raw, (int, float)):
            return None
        return float(self.cfg.to_ha(raw))

    async def async_set_native_value(self, value: float) -> None:
        if not self.cfg.min <= value <= self.cfg.max:
            raise HomeAssistantError(f"{value} is outside {self.cfg.min}..{self.cfg.max}")
        raw = self.cfg.to_raw(value)
        await self.coordinator.async_write(self.cfg.tag, coerce_for_write(raw, self.raw))
