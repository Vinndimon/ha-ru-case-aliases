"""The managed custom-sentences file and the intent handlers behind it."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from . import covers, lists
from .const import SENTENCES_FILE

_LOGGER = logging.getLogger(__name__)

HEADER = (
    "# Managed by the Russian Case Aliases integration. Changes will be overwritten;\n"
    "# switch the voice-command options off in the integration to remove this file.\n"
)
ALL_INTENTS = (*lists.INTENTS, *covers.INTENTS)


def build_yaml(list_commands: bool, cover_commands: bool) -> str | None:
    """Combined sentences for the enabled features, or None when none are enabled."""
    parts = [m.SENTENCES for m, on in ((lists, list_commands), (covers, cover_commands)) if on]
    if not parts:
        return None
    data: dict[str, Any] = {"language": "ru", "intents": {}}
    for part in parts:
        for key, value in part.items():
            data.setdefault(key, {}).update(value)
    return HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)


def _path(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("custom_sentences", "ru", SENTENCES_FILE))


def _sync_file(path: Path, content: str | None) -> bool:
    """Write or delete the file; True if it changed."""
    if content is None:
        if path.exists():
            path.unlink()
            return True
        return False
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


async def _reload_conversation(hass: HomeAssistant) -> None:
    if hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", {"language": "ru"}, blocking=True)


async def async_install(hass: HomeAssistant, list_commands: bool, cover_commands: bool) -> None:
    """Register handlers for the enabled features and bring the file in line."""
    for intent_type in ALL_INTENTS:
        intent.async_remove(hass, intent_type)
    if list_commands:
        for handler in lists.handlers():
            intent.async_register(hass, handler)
    if cover_commands:
        for handler in covers.handlers():
            intent.async_register(hass, handler)
    content = build_yaml(list_commands, cover_commands)
    if await hass.async_add_executor_job(_sync_file, _path(hass), content):
        _LOGGER.info("Updated Russian custom sentences")
        await _reload_conversation(hass)


async def async_uninstall(hass: HomeAssistant) -> None:
    """Unregister all handlers and delete the file."""
    for intent_type in ALL_INTENTS:
        intent.async_remove(hass, intent_type)
    if await hass.async_add_executor_job(_sync_file, _path(hass), None):
        await _reload_conversation(hass)


async def async_status(hass: HomeAssistant) -> dict:
    path = _path(hass)
    registered = {h.intent_type for h in intent.async_get(hass)}
    return {
        "sentences_file": str(path),
        "sentences_file_present": await hass.async_add_executor_job(path.exists),
        "intent_handlers_registered": {i: i in registered for i in ALL_INTENTS},
        "server_language": hass.config.language,
    }
