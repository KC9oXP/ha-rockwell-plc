"""Base entity."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ALLOW_WRITES, CONF_PATH, CONF_PLC_TYPE, DOMAIN, PLC_LOGIX
from .coordinator import RockwellCoordinator
from .tags import TagConfig


def entities_for(entry: ConfigEntry, platform: str, factory) -> list:
    """Build entities whose effective platform (after the write setting) is `platform`."""
    data = entry.runtime_data
    allow_writes = entry.options.get(CONF_ALLOW_WRITES, False)
    return [
        factory(data.coordinator, entry, cfg)
        for cfg in data.tags
        if cfg.effective_platform(allow_writes) == platform
    ]


class RockwellEntity(CoordinatorEntity[RockwellCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RockwellCoordinator, entry: ConfigEntry, cfg: TagConfig) -> None:
        super().__init__(coordinator)
        self.cfg = cfg
        self._attr_name = cfg.name
        self._attr_unique_id = f"{entry.entry_id}_{cfg.key}"
        if cfg.icon:
            self._attr_icon = cfg.icon
        info = coordinator.client.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Rockwell Automation / Allen-Bradley",
            model=str(info.get("product_name") or ("Logix 5000" if entry.data[CONF_PLC_TYPE] == PLC_LOGIX else "SLC / MicroLogix")),
            sw_version=str(info["revision"]) if info.get("revision") else None,
            serial_number=str(info["serial"]) if info.get("serial") else None,
            configuration_url=None,
        )
        self._attr_extra_state_attributes = {"plc_tag": cfg.tag, "plc_path": entry.data[CONF_PATH]}

    @property
    def raw(self) -> Any:
        return self.coordinator.last_raw(self.cfg.tag)

    @property
    def available(self) -> bool:
        if not super().available or not self.coordinator.data:
            return False
        val = self.coordinator.data.get(self.cfg.tag)
        return val is not None and val.error is None
