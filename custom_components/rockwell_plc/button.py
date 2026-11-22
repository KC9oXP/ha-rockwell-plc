"""Buttons: momentary pushbuttons (write press_value, wait pulse_ms, write release_value)."""

from __future__ import annotations

import asyncio

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import RockwellEntity, entities_for


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(entities_for(entry, "button", RockwellButton))


class RockwellButton(RockwellEntity, ButtonEntity):
    @property
    def available(self) -> bool:
        # Button tags are not polled; available whenever the PLC connection is healthy.
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        await self.coordinator.async_write(self.cfg.tag, self.cfg.press_value, refresh=False)
        if self.cfg.pulse_ms > 0:
            try:
                await asyncio.sleep(self.cfg.pulse_ms / 1000)
            finally:
                # Always try to release, even if HA is cancelling the task.
                await self.coordinator.async_write(self.cfg.tag, self.cfg.release_value)
