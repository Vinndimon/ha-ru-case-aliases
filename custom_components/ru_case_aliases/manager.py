"""Keeps Russian case-form aliases in sync with entity/area names and Assist exposure."""
from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
from typing import Any

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from . import morph
from .const import ASSISTANT, COVER_EXCLUDED_CASES, DEBOUNCE_SECONDS, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

# Entity registry changes that can affect the name or the Assist exposure.
_RELEVANT_CHANGES = {"name", "original_name", "options"}


def _merge(current: Iterable[Any], previous_generated: set[str], forms: set[str]) -> tuple[list, set[str]]:
    """Return (new alias list, aliases we generated).

    Aliases the user added by hand are kept; aliases we generated earlier but no longer
    want (e.g. after a rename) are removed.
    """
    kept = [a for a in current if not (isinstance(a, str) and a in previous_generated)]
    have = {a.lower() for a in kept if isinstance(a, str)}
    generated = {f for f in forms if f not in have}
    return kept + sorted(generated), generated


class AliasManager:
    """Generates and tracks aliases."""

    def __init__(self, hass: HomeAssistant, plural: bool, areas: bool) -> None:
        self.hass = hass
        self.plural = plural
        self.areas = areas
        self._store: Store[dict[str, dict[str, list[str]]]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._generated: dict[str, dict[str, list[str]]] = {"entities": {}, "areas": {}}
        self._pending_entities: set[str] = set()
        self._pending_all = False
        self._pending_areas = False
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._unsubs: list[Callable[[], None]] = []
        self.last_errors: dict[str, str] = {}
        self.last_run: str | None = None

    # ---------------------------------------------------------------- lifecycle
    async def async_start(self) -> None:
        self._generated = await self._store.async_load() or {}
        self._generated.setdefault("entities", {})
        self._generated.setdefault("areas", {})
        await self.hass.async_add_executor_job(morph.get_morph)  # load dictionaries off the loop
        self._unsubs.append(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._on_entity_event)
        )
        if self.areas:
            self._unsubs.append(
                self.hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, self._on_area_event)
            )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None

    async def async_flush(self) -> None:
        """Persist tracking data now (on unload, so removal sees the latest state)."""
        await self._store.async_save(self._generated)

    @property
    def paused(self) -> bool:
        return bool(self._generated.get("paused"))

    def _strip_all(self) -> int:
        """Remove every alias this integration added; return how many items changed."""
        ent_reg, area_reg = er.async_get(self.hass), ar.async_get(self.hass)
        changed = 0
        for entity_id, prev in self._generated.get("entities", {}).items():
            if entry := ent_reg.async_get(entity_id):
                aliases, _ = _merge(entry.aliases, set(prev), set())
                ent_reg.async_update_entity(entity_id, aliases=type(entry.aliases)(aliases))
                changed += 1
        for area_id, prev in self._generated.get("areas", {}).items():
            if area := area_reg.async_get_area(area_id):
                aliases, _ = _merge(area.aliases, set(prev), set())
                area_reg.async_update(area_id, aliases=type(area.aliases)(aliases))
                changed += 1
        self._generated["entities"], self._generated["areas"] = {}, {}
        return changed

    async def async_revert(self) -> int:
        """Remove all generated aliases and pause until regenerate is called."""
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None
        self._pending_entities.clear()
        self._pending_all = self._pending_areas = False
        changed = self._strip_all()
        self._generated["paused"] = True
        await self._store.async_save(self._generated)
        _LOGGER.info("Reverted: removed generated aliases from %d item(s)", changed)
        return changed

    async def async_resume(self) -> None:
        if self.paused:
            self._generated["paused"] = False
            await self._store.async_save(self._generated)

    async def async_remove_all(self) -> None:
        """Remove every alias this integration added (used when it is deleted)."""
        self._generated = await self._store.async_load() or {}
        self._generated.setdefault("entities", {})
        self._generated.setdefault("areas", {})
        self._strip_all()
        await self._store.async_remove()

    # ------------------------------------------------------------------- events
    @callback
    def _on_entity_event(self, event: Event) -> None:
        if self.paused:
            return
        data = event.data
        action = data.get("action")
        if action == "remove":
            self._generated["entities"].pop(data["entity_id"], None)
            self._store.async_delay_save(lambda: self._generated, 10)
            return
        if action == "update" and not _RELEVANT_CHANGES & set(data.get("changes", {})):
            return  # e.g. our own alias write — ignore to avoid loops
        self.schedule(entity_ids=[data["entity_id"]])

    @callback
    def _on_area_event(self, event: Event) -> None:
        if not self.paused and event.data.get("action") in ("create", "update"):
            self.schedule(areas=True)

    @callback
    def schedule(self, entity_ids: Iterable[str] | None = None, areas: bool = False) -> None:
        """Debounce work; entity_ids=None means all entities."""
        if self.paused:
            return
        if entity_ids is None:
            self._pending_all = True
        else:
            self._pending_entities.update(entity_ids)
        self._pending_areas |= areas and self.areas
        if self._cancel_timer is None:
            self._cancel_timer = async_call_later(self.hass, DEBOUNCE_SECONDS, self._run)

    # --------------------------------------------------------------------- work
    async def _run(self, _now: Any = None) -> None:
        self._cancel_timer = None
        try:
            await self._run_inner()
        except Exception as err:  # noqa: BLE001 - log instead of dying silently in a timer
            _LOGGER.exception("Alias update failed")
            self.last_errors["_run"] = f"{type(err).__name__}: {err}"

    async def _run_inner(self) -> None:
        do_all, ids, do_areas = self._pending_all, set(self._pending_entities), self._pending_areas
        self._pending_all, self._pending_areas = False, False
        self._pending_entities.clear()

        ent_reg = er.async_get(self.hass)
        targets = set(ent_reg.entities) if do_all else ids
        if do_all:
            targets |= set(self._generated["entities"])  # so stale ones get cleaned up

        entries = [e for eid in targets if (e := ent_reg.async_get(eid))]
        # Russian names of entities named by their integration (e.g. the shopping list), for
        # servers whose language is not Russian: Assist only knows "Shopping List" there.
        platforms = {e.platform for e in entries if not e.name and e.translation_key}
        ru_translations = (
            await async_get_translations(self.hass, "ru", "entity", platforms) if platforms else {}
        )
        dev_reg = dr.async_get(self.hass)

        names: dict[str, str] = {}
        add_nominative: set[str] = set()
        for entry in entries:
            entity_id = entry.entity_id
            try:
                name, translated = self._entity_name(entry, ru_translations, dev_reg)
                exposed = async_should_expose(self.hass, ASSISTANT, entity_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Skipping %s: %s", entity_id, err)
                self.last_errors[entity_id] = f"name/exposure: {type(err).__name__}: {err}"
                continue
            if name and morph.is_russian(name) and exposed:
                names[entity_id] = name
                if translated:
                    add_nominative.add(entity_id)
            else:
                names[entity_id] = ""  # not exposed / not Russian: remove our aliases

        area_names: dict[str, str] = {}
        if do_areas:
            for area in ar.async_get(self.hass).async_list_areas():
                area_names[area.id] = area.name if morph.is_russian(area.name) else ""

        to_inflect = {f"e:{k}": v for k, v in names.items() if v}
        to_inflect |= {f"a:{k}": v for k, v in area_names.items() if v}
        # Covers: no genitive and no plural. «Шторы» (gen. sg. = nom. pl. of «штора») as an alias
        # would turn «закрой шторы» into a command for that single cover.
        covers = {f"e:{eid}" for eid in names if eid.startswith("cover.")}
        forms, errors = await self.hass.async_add_executor_job(
            morph.batch_case_forms,
            {k: v for k, v in to_inflect.items() if k[0] == "e" and k not in covers},
            self.plural,
        )
        cover_forms, cover_errors = await self.hass.async_add_executor_job(
            morph.batch_case_forms,
            {k: v for k, v in to_inflect.items() if k in covers},
            False,
            COVER_EXCLUDED_CASES,
        )
        forms |= cover_forms
        errors |= cover_errors
        area_forms, area_errors = await self.hass.async_add_executor_job(
            morph.batch_case_forms, {k: v for k, v in to_inflect.items() if k[0] == "a"}, False
        )
        forms |= area_forms
        for key, err in (errors | area_errors).items():
            _LOGGER.warning("Could not inflect %s «%s»: %s", key[2:], to_inflect[key], err)
            self.last_errors[key[2:]] = f"inflection: {err}"

        for entity_id in add_nominative:  # Assist doesn't know the Russian name itself yet
            forms.setdefault(f"e:{entity_id}", set()).add(names[entity_id].lower())

        changed = 0
        for entity_id in names:
            if f"e:{entity_id}" in errors:
                continue  # keep previous aliases rather than wiping them
            try:
                changed += self._apply_entity(ent_reg, entity_id, forms.get(f"e:{entity_id}", set()))
                self.last_errors.pop(entity_id, None)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not update aliases of %s: %s", entity_id, err)
                self.last_errors[entity_id] = f"update: {type(err).__name__}: {err}"
        area_reg = ar.async_get(self.hass)
        for area_id in area_names:
            if f"a:{area_id}" in area_errors:
                continue
            try:
                changed += self._apply_area(area_reg, area_id, forms.get(f"a:{area_id}", set()))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not update aliases of area %s: %s", area_id, err)
                self.last_errors[f"area:{area_id}"] = f"update: {type(err).__name__}: {err}"

        self.last_run = dt_util.utcnow().isoformat()
        if changed:
            _LOGGER.info("Updated Russian case aliases on %d item(s)", changed)
        self._store.async_delay_save(lambda: self._generated, 5)

    def _entity_name(
        self, entry: er.RegistryEntry, ru_translations: dict[str, str], dev_reg: dr.DeviceRegistry
    ) -> tuple[str | None, bool]:
        """Return (Russian name to inflect, whether it differs from the name Assist knows)."""
        if entry.name:
            return entry.name, False  # set by the user; Assist uses it as is
        state = self.hass.states.get(entry.entity_id)
        assist_name = (state.name if state else None) or entry.original_name
        if assist_name and morph.is_russian(assist_name):
            return assist_name, False
        ru_part = None
        if entry.translation_key:
            ru_part = ru_translations.get(
                f"component.{entry.platform}.entity.{entry.domain}.{entry.translation_key}.name"
            )
        if not ru_part:
            return assist_name, False
        name = ru_part
        if entry.has_entity_name and entry.device_id and (device := dev_reg.async_get(entry.device_id)):
            if device_name := device.name_by_user or device.name:
                name = f"{device_name} {ru_part}"
        return name, name.lower() != (assist_name or "").lower()

    def _apply_entity(self, ent_reg: er.EntityRegistry, entity_id: str, forms: set[str]) -> int:
        entry = ent_reg.async_get(entity_id)
        if entry is None:
            return 0
        prev = set(self._generated["entities"].get(entity_id, []))
        aliases, generated = _merge(entry.aliases, prev, forms)
        if generated:
            self._generated["entities"][entity_id] = sorted(generated)
        else:
            self._generated["entities"].pop(entity_id, None)
        if sorted(map(str, aliases)) == sorted(map(str, entry.aliases)):
            return 0
        ent_reg.async_update_entity(entity_id, aliases=type(entry.aliases)(aliases))
        return 1

    def _apply_area(self, area_reg: ar.AreaRegistry, area_id: str, forms: set[str]) -> int:
        area = area_reg.async_get_area(area_id)
        if area is None:
            return 0
        prev = set(self._generated["areas"].get(area_id, []))
        aliases, generated = _merge(area.aliases, prev, forms)
        if generated:
            self._generated["areas"][area_id] = sorted(generated)
        else:
            self._generated["areas"].pop(area_id, None)
        if sorted(map(str, aliases)) == sorted(map(str, area.aliases)):
            return 0
        area_reg.async_update(area_id, aliases=type(area.aliases)(aliases))
        return 1

    # -------------------------------------------------------------- diagnostics
    async def async_diagnose(self, entity_ids: list[str] | None) -> dict[str, Any]:
        """What the integration sees for the given entities (default: all to-do lists)."""
        hass = self.hass
        ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
        if not entity_ids:
            entity_ids = sorted({s.entity_id for s in hass.states.async_all("todo")}
                                | {e.entity_id for e in ent_reg.entities.values() if e.domain == "todo"})
        entries = [e for eid in entity_ids if (e := ent_reg.async_get(eid))]
        platforms = {e.platform for e in entries if e.translation_key}
        ru_tr = await async_get_translations(hass, "ru", "entity", platforms) if platforms else {}

        # every exposed name Assist knows, to spot duplicates across domains
        known: dict[str, list[str]] = {}
        for state in hass.states.async_all():
            if not async_should_expose(hass, ASSISTANT, state.entity_id):
                continue
            entry = ent_reg.async_get(state.entity_id)
            for n in [state.name, *((entry.aliases if entry else None) or [])]:
                if isinstance(n, str) and n.strip():
                    known.setdefault(n.strip().lower(), []).append(state.entity_id)

        report: dict[str, Any] = {}
        for entity_id in entity_ids:
            entry = ent_reg.async_get(entity_id)
            state = hass.states.get(entity_id)
            info: dict[str, Any] = {
                "in_entity_registry": entry is not None,
                "state_name": state.name if state else None,
                "exposed_to_assist": async_should_expose(hass, ASSISTANT, entity_id),
            }
            if entry:
                name, translated = self._entity_name(entry, ru_tr, dev_reg)
                info |= {
                    "platform": entry.platform,
                    "registry_name": entry.name,
                    "original_name": entry.original_name,
                    "translation_key": entry.translation_key,
                    "name_used": name,
                    "name_is_russian": bool(name and morph.is_russian(name)),
                    "aliases": sorted(a if isinstance(a, str) else "<entity name>" for a in entry.aliases),
                    "added_by_integration": self._generated["entities"].get(entity_id, []),
                }
                if name and morph.is_russian(name):
                    loct = await hass.async_add_executor_job(morph.inflect_phrase, name, "loct")
                    for spoken in {name.lower(), loct}:
                        others = [e for e in known.get(spoken, []) if e != entity_id]
                        if others:
                            info.setdefault("same_name_as", {})[spoken] = others
            if entity_id in self.last_errors:
                info["last_error"] = self.last_errors[entity_id]
            report[entity_id] = info
        return {
            "paused": self.paused,
            "last_run": self.last_run,
            "errors_in_last_run": dict(self.last_errors),
            "entities": report,
        }
