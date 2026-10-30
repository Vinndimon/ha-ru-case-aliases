"""Russian Case Aliases: adds declined forms of Russian names as Assist aliases."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

from homeassistant.helpers import config_validation as cv

from . import sentences
from .const import (
    CONF_AREAS, CONF_COVER_COMMANDS, CONF_LIST_COMMANDS, CONF_PLURAL, DEFAULT_AREAS,
    DEFAULT_COVER_COMMANDS, DEFAULT_LIST_COMMANDS,
    DEFAULT_PLURAL, DOMAIN, SERVICE_DIAGNOSE, SERVICE_REGENERATE, SERVICE_REVERT,
)
from .manager import AliasManager

type RuAliasesConfigEntry = ConfigEntry[AliasManager]


def _manager(hass: HomeAssistant, entry: ConfigEntry) -> AliasManager:
    return AliasManager(
        hass,
        plural=entry.options.get(CONF_PLURAL, DEFAULT_PLURAL),
        areas=entry.options.get(CONF_AREAS, DEFAULT_AREAS),
    )


def _list_commands(entry: ConfigEntry) -> bool:
    return entry.options.get(CONF_LIST_COMMANDS, DEFAULT_LIST_COMMANDS)


def _cover_commands(entry: ConfigEntry) -> bool:
    return entry.options.get(CONF_COVER_COMMANDS, DEFAULT_COVER_COMMANDS)


async def _install_sentences(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await sentences.async_install(hass, _list_commands(entry), _cover_commands(entry))


async def async_setup_entry(hass: HomeAssistant, entry: RuAliasesConfigEntry) -> bool:
    manager = _manager(hass, entry)
    await manager.async_start()
    entry.runtime_data = manager

    def _full_scan(_event=None) -> None:
        manager.schedule(entity_ids=None, areas=True)

    if not manager.paused:
        await _install_sentences(hass, entry)
        if hass.state is CoreState.running:
            _full_scan()
        else:
            entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _full_scan))

    async def _regenerate(_call: ServiceCall) -> None:
        await manager.async_resume()
        await _install_sentences(hass, entry)
        _full_scan()

    async def _revert(_call: ServiceCall) -> ServiceResponse:
        changed = await manager.async_revert()
        await sentences.async_uninstall(hass)
        return {"items_changed": changed}

    async def _diagnose(call: ServiceCall) -> ServiceResponse:
        report = await manager.async_diagnose(call.data.get("entity_id"))
        report["voice_commands"] = {
            "list_commands_enabled": _list_commands(entry),
            "cover_commands_enabled": _cover_commands(entry),
            **await sentences.async_status(hass),
        }
        return report

    hass.services.async_register(DOMAIN, SERVICE_REGENERATE, _regenerate)
    hass.services.async_register(
        DOMAIN, SERVICE_DIAGNOSE, _diagnose,
        schema=vol.Schema({vol.Optional("entity_id"): cv.entity_ids}),
        supports_response=SupportsResponse.ONLY,
    )
    entry.async_on_unload(lambda: hass.services.async_remove(DOMAIN, SERVICE_DIAGNOSE))
    hass.services.async_register(
        DOMAIN, SERVICE_REVERT, _revert, supports_response=SupportsResponse.OPTIONAL
    )
    entry.async_on_unload(lambda: hass.services.async_remove(DOMAIN, SERVICE_REGENERATE))
    entry.async_on_unload(lambda: hass.services.async_remove(DOMAIN, SERVICE_REVERT))
    entry.async_on_unload(manager.async_stop)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: RuAliasesConfigEntry) -> bool:
    await entry.runtime_data.async_flush()
    await sentences.async_uninstall(hass)  # no handlers -> no sentences
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Integration deleted: take back every alias and the sentences file."""
    await _manager(hass, entry).async_remove_all()
    await sentences.async_uninstall(hass)
