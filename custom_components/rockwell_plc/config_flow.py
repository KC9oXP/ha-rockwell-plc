"""Config and options flow."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .const import (
    CONF_ALLOW_SERVICE_WRITES,
    CONF_ALLOW_WRITES,
    CONF_PATH,
    CONF_PLC_TYPE,
    CONF_SCAN_INTERVAL,
    CONF_TAGS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    PLC_LOGIX,
    PLC_TYPES,
)
from .plc import PLCClient, PLCError
from .tags import TagConfigError, parse_tags

_LOGGER = logging.getLogger(__name__)

EXAMPLE_TAGS = """# One entry per tag. Delete these examples and add your own.
# platform: sensor | binary_sensor | switch | number | button
# - tag: Tank1_Level
#   name: Tank 1 Level
#   platform: sensor
#   unit: "%"
#   scale: 0.1
#   state_class: measurement
# - tag: Pump1_Running
#   platform: binary_sensor
"""


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=3600, step=0.5, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(CONF_ALLOW_WRITES, default=defaults.get(CONF_ALLOW_WRITES, False)): BooleanSelector(),
            vol.Required(
                CONF_ALLOW_SERVICE_WRITES, default=defaults.get(CONF_ALLOW_SERVICE_WRITES, False)
            ): BooleanSelector(),
            vol.Optional(CONF_TAGS, default=defaults.get(CONF_TAGS, EXAMPLE_TAGS)): TextSelector(
                TextSelectorConfig(multiline=True)
            ),
        }
    )


def _validate_options(user_input: dict[str, Any]) -> tuple[dict[str, str], str]:
    try:
        parse_tags(user_input.get(CONF_TAGS, ""))
    except TagConfigError as err:
        return {CONF_TAGS: "invalid_tags"}, str(err)
    return {}, ""


class RockwellConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            path = user_input[CONF_PATH].strip()
            await self.async_set_unique_id(path.lower())
            self._abort_if_unique_id_configured()
            client = PLCClient(user_input[CONF_PLC_TYPE], path)
            try:
                info = await self.hass.async_add_executor_job(client.connect)
            except PLCError as err:
                _LOGGER.warning("Connection test to %s failed: %s", path, err)
                errors["base"] = "cannot_connect"
                placeholders["error"] = str(err)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error testing %s", path)
                errors["base"] = "unknown"
            else:
                self._data = {CONF_PATH: path, CONF_PLC_TYPE: user_input[CONF_PLC_TYPE]}
                self._title = user_input.get(CONF_NAME) or info.get("name") or info.get("product_name") or path
                return await self.async_step_options()
            finally:
                await self.hass.async_add_executor_job(client.close)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, "")): str,
                vol.Required(CONF_PATH, default=(user_input or {}).get(CONF_PATH, "")): str,
                vol.Required(CONF_PLC_TYPE, default=(user_input or {}).get(CONF_PLC_TYPE, PLC_LOGIX)): SelectSelector(
                    SelectSelectorConfig(options=PLC_TYPES, translation_key="plc_type", mode=SelectSelectorMode.LIST)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors, description_placeholders=placeholders)

    async def async_step_options(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            errors, detail = _validate_options(user_input)
            if not errors:
                return self.async_create_entry(title=self._title, data=self._data, options=user_input)
        return self.async_show_form(
            step_id="options",
            data_schema=_options_schema(user_input or {}),
            errors=errors,
            description_placeholders={"error": detail},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RockwellOptionsFlow()


class RockwellOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            errors, detail = _validate_options(user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or dict(self.config_entry.options)),
            errors=errors,
            description_placeholders={"error": detail},
        )
