"""Tests for Russian Case Aliases."""
from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er
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


def _aliases(hass, entity_id):
    return {a for a in er.async_get(hass).async_get(entity_id).aliases if isinstance(a, str)}


async def test_lifecycle(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    ent_reg = er.async_get(hass)
    lamp = ent_reg.async_get_or_create("light", "test", "lamp1")
    ent_reg.async_update_entity(lamp.entity_id, name="Настольная лампа", aliases={"торшер"})
    other = ent_reg.async_get_or_create("light", "test", "lamp2")
    ent_reg.async_update_entity(other.entity_id, name="Кухонная люстра")
    async_expose_entity(hass, "conversation", lamp.entity_id, True)
    async_expose_entity(hass, "conversation", other.entity_id, False)
    area = ar.async_get(hass).async_create("Спальня")

    entry = MockConfigEntry(domain=DOMAIN, options={"plural": True, "areas": True})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _tick(hass)

    aliases = _aliases(hass, lamp.entity_id)
    assert {"настольную лампу", "настольные лампы", "настольных ламп", "торшер"} <= aliases
    assert "настольных лампы" not in aliases
    assert _aliases(hass, other.entity_id) == set()  # not exposed
    assert {"спальню", "спальне"} <= ar.async_get(hass).async_get_area(area.id).aliases

    # Rename: old generated forms go, manual alias stays
    ent_reg.async_update_entity(lamp.entity_id, name="Лампа")
    await _tick(hass)
    aliases = _aliases(hass, lamp.entity_id)
    assert {"лампу", "ламп", "торшер"} <= aliases
    assert "настольную лампу" not in aliases

    # Exposing the other entity later adds its forms
    async_expose_entity(hass, "conversation", other.entity_id, True)
    await _tick(hass)
    assert "кухонную люстру" in _aliases(hass, other.entity_id)

    # Unexpose: our aliases removed, manual kept
    async_expose_entity(hass, "conversation", lamp.entity_id, False)
    await _tick(hass)
    assert _aliases(hass, lamp.entity_id) == {"торшер"}

    # Removing the integration cleans up everything it added
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _aliases(hass, other.entity_id) == set()
    assert ar.async_get(hass).async_get_area(area.id).aliases == set()
