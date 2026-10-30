"""Config flow for Russian Case Aliases."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_AREAS, CONF_COVER_COMMANDS, CONF_LIST_COMMANDS, CONF_PLURAL, DEFAULT_AREAS,
    DEFAULT_COVER_COMMANDS, DEFAULT_LIST_COMMANDS, DEFAULT_PLURAL, DOMAIN,
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_PLURAL, default=defaults.get(CONF_PLURAL, DEFAULT_PLURAL)): bool,
        vol.Required(CONF_AREAS, default=defaults.get(CONF_AREAS, DEFAULT_AREAS)): bool,
        vol.Required(
            CONF_LIST_COMMANDS, default=defaults.get(CONF_LIST_COMMANDS, DEFAULT_LIST_COMMANDS)
        ): bool,
        vol.Required(
            CONF_COVER_COMMANDS, default=defaults.get(CONF_COVER_COMMANDS, DEFAULT_COVER_COMMANDS)
        ): bool,
    })


class RuCaseAliasesConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Russian Case Aliases", data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RuCaseAliasesOptionsFlow()


class RuCaseAliasesOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(dict(self.config_entry.options)))
