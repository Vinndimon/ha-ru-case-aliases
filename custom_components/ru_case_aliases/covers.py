"""«закрой/открой шторы» for every kind of curtain, including roller shades.

Home Assistant maps «шторы» to the *curtain* device class only («рулонные шторы» is *shade*), but
people say «шторы» for both. These sentences override the built-in ones (custom sentences win) and
act on all covers of SHADE_DEVICE_CLASSES in the room, a named area, a floor, or the whole home.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.helpers import config_validation as cv, intent

from .const import INTENT_SHADES_CLOSE, INTENT_SHADES_OPEN, SHADE_DEVICE_CLASSES

INTENTS = (INTENT_SHADES_CLOSE, INTENT_SHADES_OPEN)

_HERE = "[ здесь| в (комнате|помещении)]"
_HOME = "(в доме|во (всем|всём) доме|дома|везде)"


def _blocks(verb: str) -> list[dict[str, Any]]:
    return [
        {   # the satellite's room
            "sentences": [f"<{verb}> [все] <ru_shades>{_HERE}", f"<{verb}>{_HERE} [все] <ru_shades>"],
            "requires_context": {"area": {"slot": True}},
        },
        {"sentences": [
            f"<{verb}> [все] <ru_shades> [в|во|на] {{area}}",
            f"<{verb}> [в|во|на] {{area}} [все] <ru_shades>",
        ]},
        {"sentences": [f"<{verb}> [все] <ru_shades> [на] {{floor}} [этаж[е]]"]},
        {"sentences": [f"<{verb}> [все] <ru_shades> {_HOME}", f"<{verb}> {_HOME} [все] <ru_shades>"]},
    ]


SENTENCES: dict[str, Any] = {
    "intents": {
        INTENT_SHADES_CLOSE: {"data": _blocks("ru_close")},
        INTENT_SHADES_OPEN: {"data": _blocks("ru_open")},
    },
    "expansion_rules": {
        "ru_close": "(закр(ой|ыть)|прикр(ой|ыть)|опусти[ть]|задерн(и|уть)|задёрн(и|уть))",
        "ru_open": "(откр(ой|ыть)|подними|поднять|раздвинь|раздвинуть|отдерн(и|уть)|отдёрн(и|уть))",
        "ru_shades": "(штор(ы|у)|шторк(и|у)|занавеск(и|у))",
    },
}


class ShadesIntent(intent.IntentHandler):
    """Open or close every curtain/roller shade in the targeted place."""

    slot_schema = {vol.Optional("area"): cv.string, vol.Optional("floor"): cv.string}
    platforms = {"cover"}

    def __init__(self, intent_type: str, service: str, doing: str) -> None:
        self.intent_type = intent_type
        self.description = f"{service} all curtains and roller shades (Russian)"
        self._service = service
        self._doing = doing

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        area = slots.get("area", {}).get("value")
        floor = slots.get("floor", {}).get("value")

        match = intent.async_match_targets(
            hass,
            intent.MatchTargetsConstraints(
                area_name=area, floor_name=floor, domains={"cover"},
                device_classes=set(SHADE_DEVICE_CLASSES), assistant=intent_obj.assistant,
            ),
        )
        response = intent_obj.create_response()
        if not match.is_match or not match.states:
            response.async_set_speech("Не нашёл штор.")
            return response

        await hass.services.async_call(
            "cover", self._service, target={"entity_id": [s.entity_id for s in match.states]},
            blocking=False, context=intent_obj.context,
        )
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.async_set_states(matched_states=match.states)
        response.async_set_speech(f"{self._doing} шторы.")
        return response


def handlers() -> list[intent.IntentHandler]:
    return [
        ShadesIntent(INTENT_SHADES_CLOSE, "close_cover", "Закрываю"),
        ShadesIntent(INTENT_SHADES_OPEN, "open_cover", "Открываю"),
    ]
