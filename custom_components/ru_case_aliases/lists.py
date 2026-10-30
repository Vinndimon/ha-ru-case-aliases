"""Russian voice commands for to-do lists that Home Assistant doesn't ship yet.

- reading:  «что в списке покупок», «прочитай список покупок»
- removing: «удали хлеб из списка покупок», «убери колбасу из списка покупок»

{name} matches list names *and aliases*, so «в списке покупок» / «из списка покупок» work thanks
to the case-form aliases this integration generates.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import config_validation as cv, intent

from . import morph
from .const import INTENT_LIST_GET_ITEMS, INTENT_LIST_REMOVE_ITEM, MAX_SPOKEN_ITEMS

INTENTS = (INTENT_LIST_GET_ITEMS, INTENT_LIST_REMOVE_ITEM)

SENTENCES: dict[str, Any] = {
    "intents": {
        INTENT_LIST_GET_ITEMS: {"data": [{
            "sentences": [
                "что [ещё] [есть|лежит|записано|осталось|у меня] в [мо(ём|ем)] {name}",
                "(прочитай|прочти|зачитай|озвучь|покажи|перечисли) [мой] {name}",
                "какие (пункты|покупки|задачи|дела) [есть|остались] в [мо(ём|ем)] {name}",
            ],
            "requires_context": {"domain": "todo"},
        }]},
        INTENT_LIST_REMOVE_ITEM: {"data": [{
            "sentences": ["(удали|удалить|убери|убрать|сотри) {ru_list_item:item} из [моего] {name}"],
            "requires_context": {"domain": "todo"},
        }]},
    },
    "lists": {"ru_list_item": {"wildcard": True}},
}


def handlers() -> list[intent.IntentHandler]:
    return [ListGetItemsIntent(), ListRemoveItemIntent()]


# ------------------------------------------------------------------- helpers
def _find_list(intent_obj: intent.Intent, name: str) -> State | None:
    match = intent.async_match_targets(
        intent_obj.hass,
        intent.MatchTargetsConstraints(name=name, domains={"todo"}, assistant=intent_obj.assistant),
    )
    return match.states[0] if match.is_match and match.states else None


async def _list_phrase(hass: HomeAssistant, state: State, spoken: str, case: str) -> str:
    """The list name in the given case («списке покупок», «списка покупок»)."""
    base = state.name if morph.is_russian(state.name or "") else spoken
    try:
        return await hass.async_add_executor_job(morph.inflect_phrase, base, case)
    except Exception:  # noqa: BLE001 - never fail the answer over grammar
        return spoken


async def _get_items(intent_obj: intent.Intent, entity_id: str, statuses: list[str]) -> list[dict]:
    result = await intent_obj.hass.services.async_call(
        "todo", "get_items", {"entity_id": entity_id, "status": statuses},
        blocking=True, context=intent_obj.context, return_response=True,
    )
    return (result or {}).get(entity_id, {}).get("items", [])


# -------------------------------------------------------------------- intents
class ListGetItemsIntent(intent.IntentHandler):
    """Read the open items of a to-do list."""

    intent_type = INTENT_LIST_GET_ITEMS
    description = "Reads the items on a to-do list (Russian)"
    slot_schema = {vol.Required("name"): cv.string}
    platforms = {"todo"}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        name = slots["name"]["value"]
        spoken = (slots["name"].get("text") or name).strip()
        response = intent_obj.create_response()

        if (state := _find_list(intent_obj, name)) is None:
            response.async_set_speech(f"Не нашёл список «{spoken}».")
            return response

        items = [i["summary"] for i in await _get_items(intent_obj, state.entity_id, ["needs_action"])]
        where = await _list_phrase(hass, state, spoken, "loct")
        if not items:
            speech = f"В {where} ничего нет."
        elif len(items) <= MAX_SPOKEN_ITEMS:
            speech = f"В {where}: {', '.join(items)}."
        else:
            rest = len(items) - MAX_SPOKEN_ITEMS
            speech = f"В {where}: {', '.join(items[:MAX_SPOKEN_ITEMS])} и ещё {rest}."
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_states(matched_states=[state])
        response.async_set_speech(speech)
        return response


class ListRemoveItemIntent(intent.IntentHandler):
    """Remove an item from a to-do list; the item may be said in any case («колбасу» → «Колбаса»)."""

    intent_type = INTENT_LIST_REMOVE_ITEM
    description = "Removes an item from a to-do list (Russian)"
    slot_schema = {vol.Required("name"): cv.string, vol.Required("item"): cv.string}
    platforms = {"todo"}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        name = slots["name"]["value"]
        spoken = (slots["name"].get("text") or name).strip()
        item_spoken = slots["item"]["value"].strip()
        response = intent_obj.create_response()

        if (state := _find_list(intent_obj, name)) is None:
            response.async_set_speech(f"Не нашёл список «{spoken}».")
            return response

        items = await _get_items(intent_obj, state.entity_id, ["needs_action", "completed"])
        summaries = [i["summary"] for i in items]
        index = await hass.async_add_executor_job(morph.match_item, item_spoken, summaries)
        if index is None:
            where = await _list_phrase(hass, state, spoken, "loct")
            response.async_set_speech(f"В {where} отсутствует «{item_spoken}».")
            return response

        item = items[index]
        await hass.services.async_call(
            "todo", "remove_item", {"item": [item.get("uid") or item["summary"]]},
            target={"entity_id": state.entity_id}, blocking=True, context=intent_obj.context,
        )
        source = await _list_phrase(hass, state, spoken, "gent")
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.async_set_states(matched_states=[state])
        response.async_set_speech(f"Удалил {item_spoken} из {source}.")
        return response
