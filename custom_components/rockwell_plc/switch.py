"""Switches: writable BOOL tags. Only created when writes are enabled."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RockwellEntity, entities_for
from .tags import coerce_for_write


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(entities_for(entry, "switch", RockwellSwitch))


class RockwellSwitch(RockwellEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        raw = self.raw
        if raw is None:
            return None
        return bool(raw) != self.cfg.invert

    async def _set(self, on: bool) -> None:
        target = on != self.cfg.invert
        last = self.raw
        await self.coordinator.async_write(self.cfg.tag, coerce_for_write(target, last if last is not None else True))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
