"""Tests for list-reading voice commands and revert."""
from datetime import timedelta
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.ru_case_aliases.const import DOMAIN, SENTENCES_FILE


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


def _aliases(hass, entity_id):
    return {a for a in er.async_get(hass).async_get(entity_id).aliases if isinstance(a, str)}


@pytest.fixture
async def setup(hass: HomeAssistant):
    hass.config.language = "ru"
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    shop = MockConfigEntry(domain="shopping_list")
    shop.add_to_hass(hass)
    assert await hass.config_entries.async_setup(shop.entry_id)
    await hass.async_block_till_done()
    er.async_get(hass).async_update_entity("todo.shopping_list", name="Список покупок")
    await hass.services.async_call("shopping_list", "clear_completed_items", {}, blocking=True)
    for item in list(hass.data["shopping_list"].items):
        await hass.data["shopping_list"].async_remove(item["id"])
    for item in ("молоко", "хлеб", "Колбаса", "Зелёный чай"):
        await hass.services.async_call(
            "todo", "add_item", {"item": item}, target={"entity_id": "todo.shopping_list"}, blocking=True
        )
    entry = MockConfigEntry(domain=DOMAIN, options={"plural": True, "areas": True, "list_commands": True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _tick(hass)
    return entry


async def test_read_shopping_list(hass: HomeAssistant, setup) -> None:
    assert {"списке покупок", "списка покупок"} <= _aliases(hass, "todo.shopping_list")
    assert Path(hass.config.path("custom_sentences", "ru", SENTENCES_FILE)).exists()

    speech = await _ask(hass, "что в списке покупок")
    assert speech == "В списке покупок: молоко, хлеб, Колбаса, Зелёный чай."
    assert await _ask(hass, "прочитай список покупок") == "В списке покупок: молоко, хлеб, Колбаса, Зелёный чай."
    assert "хлеб" in await _ask(hass, "что есть в моём списке покупок")


async def test_revert_and_regenerate(hass: HomeAssistant, setup) -> None:
    sentences = Path(hass.config.path("custom_sentences", "ru", SENTENCES_FILE))
    er.async_get(hass).async_update_entity(
        "todo.shopping_list", aliases=_aliases(hass, "todo.shopping_list") | {"покупки"}
    )

    result = await hass.services.async_call(DOMAIN, "revert", {}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert result["items_changed"] >= 1
    assert _aliases(hass, "todo.shopping_list") == {"покупки"}  # manual alias kept
    assert not sentences.exists()

    # Paused: a rename does not bring aliases back
    er.async_get(hass).async_update_entity("todo.shopping_list", name="Список дел")
    await _tick(hass)
    assert _aliases(hass, "todo.shopping_list") == {"покупки"}

    # Pause survives a reload of the integration
    await hass.config_entries.async_reload(setup.entry_id)
    await _tick(hass)
    assert _aliases(hass, "todo.shopping_list") == {"покупки"}
    assert not sentences.exists()

    # Regenerate resumes everything
    await hass.services.async_call(DOMAIN, "regenerate", {}, blocking=True)
    await _tick(hass)
    assert {"списке дел", "покупки"} <= _aliases(hass, "todo.shopping_list")
    assert sentences.exists()
    assert "молоко" in await _ask(hass, "что в списке дел")


async def test_diagnose(hass: HomeAssistant, setup) -> None:
    report = await hass.services.async_call(DOMAIN, "diagnose", {}, blocking=True, return_response=True)
    info = report["entities"]["todo.shopping_list"]
    assert info["exposed_to_assist"] is True
    assert info["name_used"] == "Список покупок"
    assert "списке покупок" in info["added_by_integration"]
    assert report["voice_commands"]["sentences_file_present"] is True
    assert all(report["voice_commands"]["intent_handlers_registered"].values())
    assert report["errors_in_last_run"] == {}



async def test_remove_items(hass: HomeAssistant, setup) -> None:
    async def items():
        r = await hass.services.async_call("todo", "get_items", {"entity_id": "todo.shopping_list"},
                                           blocking=True, return_response=True)
        return [i["summary"] for i in r["todo.shopping_list"]["items"]]

    assert await _ask(hass, "удали хлеб из списка покупок") == "Удалил хлеб из списка покупок."
    # item said in accusative, stored in nominative; ё/е spelled differently
    assert await _ask(hass, "убери колбасу из списка покупок") == "Удалил колбасу из списка покупок."
    assert await _ask(hass, "удали зеленый чай из моего списка покупок") == (
        "Удалил зеленый чай из списка покупок."
    )
    assert await items() == ["молоко"]
    assert await _ask(hass, "удали сыр из списка покупок") == "В списке покупок отсутствует «сыр»."
    assert await items() == ["молоко"]
