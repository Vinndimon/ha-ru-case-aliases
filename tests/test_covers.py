"""Covers: no genitive/plural aliases; «закрой шторы» acts on curtains and roller shades."""
from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.ru_case_aliases.const import DOMAIN

COVERS = {  # unique_id: (name, device_class, area)
    "left": ("Левая штора", "curtain", "Спальня"),
    "right": ("Правая штора", "shade", "Спальня"),  # roller shade
    "blind": ("Жалюзи", "blind", "Спальня"),
    "kitchen": ("Штора", "curtain", "Кухня"),
}


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations):
    yield


async def _tick(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def _setup(hass: HomeAssistant, cover_commands: bool = True):
    hass.config.language = "ru"
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    config = {
        uid: {"unique_id": uid, "friendly_name": name, "device_class": dc, "optimistic": True,
              "open_cover": [], "close_cover": []}
        for uid, (name, dc, _area) in COVERS.items()
    }
    assert await async_setup_component(hass, "cover", {"cover": [{"platform": "template", "covers": config}]})
    await hass.async_block_till_done()

    areas = {n: ar.async_get(hass).async_create(n) for n in ("Спальня", "Кухня")}
    ent_reg = er.async_get(hass)
    ids = {}
    for e in list(ent_reg.entities.values()):
        if e.domain == "cover":
            ent_reg.async_update_entity(e.entity_id, area_id=areas[COVERS[e.unique_id][2]].id)
            ids[e.unique_id] = e.entity_id

    sat_entry = MockConfigEntry(domain="test")
    sat_entry.add_to_hass(hass)
    satellite = dr.async_get(hass).async_get_or_create(
        config_entry_id=sat_entry.entry_id, identifiers={("test", "satellite")}
    )
    dr.async_get(hass).async_update_device(satellite.id, area_id=areas["Спальня"].id)

    entry = MockConfigEntry(domain=DOMAIN, options={
        "plural": True, "areas": True, "list_commands": True, "cover_commands": cover_commands,
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _tick(hass)
    return ids, satellite.id


async def _say(hass, text, device_id):
    result = await conversation.async_converse(hass, text, None, Context(), language="ru", device_id=device_id)
    await hass.async_block_till_done()
    return result.response.speech["plain"]["speech"]


def _set_all(hass, ids, state):
    for entity_id in ids.values():
        hass.states.async_set(entity_id, state, hass.states.get(entity_id).attributes)


def _closed(hass, ids):
    return {uid for uid, eid in ids.items() if hass.states.get(eid).state in ("closed", "closing")}


def _opened(hass, ids):
    return {uid for uid, eid in ids.items() if hass.states.get(eid).state in ("open", "opening")}


async def test_cover_aliases_have_no_genitive_or_plural(hass: HomeAssistant) -> None:
    ids, _ = await _setup(hass)
    ent_reg = er.async_get(hass)
    left = ent_reg.async_get(ids["left"]).aliases
    kitchen = ent_reg.async_get(ids["kitchen"]).aliases
    assert {"левую штору", "левой шторе", "левой шторой"} <= left
    assert not {"левой шторы", "левые шторы", "левых штор"} & left
    assert "штору" in kitchen
    assert "шторы" not in kitchen  # would hijack «закрой шторы»


async def test_shades_in_satellite_room(hass: HomeAssistant) -> None:
    ids, sat = await _setup(hass)
    _set_all(hass, ids, "open")
    assert await _say(hass, "закрой шторы", sat) == "Закрываю шторы."
    assert _closed(hass, ids) == {"left", "right"}  # curtain + roller shade; not blinds, not kitchen

    assert await _say(hass, "раздвинь шторы", sat) == "Открываю шторы."
    assert _closed(hass, ids) == set()


async def test_shades_by_area_and_home(hass: HomeAssistant) -> None:
    ids, sat = await _setup(hass)
    _set_all(hass, ids, "closed")
    await _say(hass, "открой шторы на кухне", sat)  # «кухне» is an area alias
    assert _opened(hass, ids) == {"kitchen"}

    _set_all(hass, ids, "open")
    await _say(hass, "закрой все шторы в доме", None)
    assert _closed(hass, ids) == {"left", "right", "kitchen"}


async def test_builtin_commands_untouched(hass: HomeAssistant) -> None:
    ids, sat = await _setup(hass)
    _set_all(hass, ids, "open")
    await _say(hass, "закрой жалюзи", sat)
    assert _closed(hass, ids) == {"blind"}


async def test_option_off_restores_builtin(hass: HomeAssistant) -> None:
    ids, sat = await _setup(hass, cover_commands=False)
    _set_all(hass, ids, "open")
    await _say(hass, "закрой шторы", sat)
    assert _closed(hass, ids) == {"left"}  # HA's own rule: curtains only
