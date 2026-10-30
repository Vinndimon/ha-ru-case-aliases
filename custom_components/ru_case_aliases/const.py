"""Constants for Russian Case Aliases."""

DOMAIN = "ru_case_aliases"

CONF_PLURAL = "plural"
CONF_AREAS = "areas"
DEFAULT_PLURAL = True
DEFAULT_AREAS = True

STORAGE_KEY = f"{DOMAIN}.generated"
STORAGE_VERSION = 1

# Assist ("conversation") is the assistant whose exposure we follow.
ASSISTANT = "conversation"
DEBOUNCE_SECONDS = 3
SERVICE_REGENERATE = "regenerate"
SERVICE_REVERT = "revert"
SERVICE_DIAGNOSE = "diagnose"

CONF_LIST_COMMANDS = "list_commands"
DEFAULT_LIST_COMMANDS = True
INTENT_LIST_GET_ITEMS = "RuCaseAliasesListGetItems"
INTENT_LIST_REMOVE_ITEM = "RuCaseAliasesListRemoveItem"
SENTENCES_FILE = "ru_case_aliases.yaml"
MAX_SPOKEN_ITEMS = 15

# Covers never get these forms (and never plural ones): see manager._run_inner.
COVER_EXCLUDED_CASES = ("gent",)

# «закрой/открой шторы» acts on all of these (curtains and roller shades).
CONF_COVER_COMMANDS = "cover_commands"
DEFAULT_COVER_COMMANDS = True
SHADE_DEVICE_CLASSES = ("curtain", "shade")
INTENT_SHADES_CLOSE = "RuCaseAliasesShadesClose"
INTENT_SHADES_OPEN = "RuCaseAliasesShadesOpen"
