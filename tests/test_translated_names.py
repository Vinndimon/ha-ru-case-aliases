"""Server language is not Russian: names come from translations (e.g. the shopping list)."""
from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.ru_case_aliases.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


async def _tick(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def _ask(hass: HomeAssistant, text: str) -> str:
    result = await conversation.async_converse(hass, text, None, Context(), language="ru")
    return result.response.speech["plain"]["speech"]


@pytest.mark.parametrize("server_language", ["en", "de"])
async def test_shopping_list_with_non_russian_server(hass: HomeAssistant, server_language: str) -> None:
    hass.config.language = server_language
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    shop = MockConfigEntry(domain="shopping_list")
    shop.add_to_hass(hass)
    assert await hass.config_entries.async_setup(shop.entry_id)
    for item in list(hass.data["shopping_list"].items):
        await hass.data["shopping_list"].async_remove(item["id"])
    entity_id = next(
        e.entity_id for e in er.async_get(hass).entities.values() if e.platform == "shopping_list"
    )
    await hass.services.async_call(
        "todo", "add_item", {"item": "молоко"}, target={"entity_id": entity_id}, blocking=True
    )

    entry = MockConfigEntry(domain=DOMAIN, options={"plural": True, "areas": True, "list_commands": True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _tick(hass)

    aliases = er.async_get(hass).async_get(entity_id).aliases
    assert {"список покупок", "списке покупок"} <= aliases
    assert await _ask(hass, "что в списке покупок") == "В списке покупок: молоко."
    assert await _ask(hass, "прочитай список покупок") == "В списке покупок: молоко."
