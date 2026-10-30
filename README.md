# Russian Case Aliases for Home Assistant

Russian nouns change with case and number, but Assist matches names literally:
«Лампа» is found, «включи **лампу**» or «выключи все **лампы**» may not be.
This integration adds the declined forms of your Russian entity and area names as aliases, automatically.

| Name | Aliases added |
|---|---|
| Лампа | лампу, лампы, ламп, лампе, лампой, лампам, лампами, лампах |
| Настольная лампа | настольную лампу, настольной лампы, настольные лампы, настольных ламп… |
| Свет в спальне | света в спальне, светом в спальне… (only the part before the preposition changes) |
| Спальня (area) | спальни, спальне, спальню, спальней |

## How it works

- Processes only entities **exposed to Assist**, and only names containing Cyrillic.
- Runs on startup, when an entity is added, renamed, or exposed/unexposed, and when an area changes.
- **Never touches aliases you added by hand.** It remembers which aliases it created; after a rename it
  replaces its old forms, and when an entity is unexposed it removes them.
- Deleting the integration removes every alias it added.
- Inflection by [pymorphy3](https://github.com/no-plagiarism/pymorphy3) with the OpenCorpora dictionary.

## Installation

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add this repository's URL, category **Integration**.
2. Install **Russian Case Aliases**, restart Home Assistant.
3. **Settings → Devices & services → Add integration → Russian Case Aliases.**

### Manual
Copy `custom_components/ru_case_aliases` into your `config/custom_components/` and restart.

## Voice commands for to-do and shopping lists

Home Assistant's Russian language data has sentences for *adding* to a list, but none for reading or
removing items. The integration adds them (option **Voice commands for lists**, on by default). They
work for every to-do list exposed to Assist (Shopping list, Local To-do, Google Keep, …):

- Reading: «что в списке покупок», «прочитай список покупок», «какие задачи в списке дел»
  → «В списке покупок: молоко, хлеб.» (open items only, up to 15)
- Removing: «удали хлеб из списка покупок», «убери колбасу из моего списка покупок»
  → «Удалил колбасу из списка покупок.» The item can be said in any case and with е instead of ё:
  «колбасу» finds «Колбаса», «зеленый чай» finds «Зелёный чай».

The sentences live in `config/custom_sentences/ru/ru_case_aliases.yaml`, which the integration manages
itself; don't edit it.

## «Закрой шторы» for curtains and roller shades

Home Assistant maps «шторы» to the *curtain* device class only; roller shades (*shade*) answer to
«рулонные шторы». People say «шторы» for both, so the integration replaces that command (option
**«Закрой/открой шторы» acts on curtains and roller shades**, on by default):

- «закрой шторы», «задёрни шторы», «открой шторки», «раздвинь шторы»: all curtains and roller shades
  in the room of the voice satellite (assign the satellite to an area)
- «закрой шторы в спальне», «открой шторы на кухне», «закрой шторы на втором этаже»
- «закрой все шторы в доме / дома / везде»

Blinds («жалюзи»), shutters and the rest keep Home Assistant's own commands. Typed commands in the app
have no room, so name the room there.

Covers get no genitive and no plural aliases: «шторы» is both the genitive singular and the plural of
«штора», and as an alias it would make «закрой шторы» target that single cover.

## Options
- **Include plural forms** (default on)
- **Also add case forms for area names** (default on)
- **Voice commands for lists** (default on)
- **«Закрой/открой шторы» acts on curtains and roller shades** (default on)

## Actions
- `ru_case_aliases.revert` removes **every** alias and the list sentences the integration added, keeps
  your own aliases, and **pauses** the integration (also across restarts), so nothing is re-added.
  Returns how many entities/areas were changed.
- `ru_case_aliases.regenerate` resumes after a revert and recalculates everything.
- `ru_case_aliases.diagnose` shows what the integration sees for the selected entities (default: all
  to-do lists): the name it uses, whether it's exposed to Assist, current and generated aliases,
  other exposed entities with the same name, errors from the last run, and whether the
  voice-command sentences and handlers are installed. Run it from **Developer Tools → Actions** when something
  doesn't match, and include the output in bug reports.

Entity names created by integrations (like the shopping list) are taken from the Russian translation
even when the server language is not Russian, and the Russian name itself is added as an alias.

## Limitations
Brand names, abbreviations and slang may be inflected incorrectly or not at all. Check the aliases in
the entity settings; if a generated form is wrong, rename the entity or turn plural forms off.
