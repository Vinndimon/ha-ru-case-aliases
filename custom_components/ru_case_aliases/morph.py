"""Russian case-form generation (blocking; run in an executor)."""
from __future__ import annotations

import pymorphy3

CASES = ("nomn", "gent", "datv", "accs", "ablt", "loct")
# After one of these the rest of the name is a dependent phrase ("Свет в спальне") and stays as is.
STOP_WORDS = frozenset({
    "в", "во", "на", "у", "над", "под", "за", "возле", "около", "с", "со",
    "из", "для", "при", "перед", "от", "до", "к", "по",
})

_MORPH: pymorphy3.MorphAnalyzer | None = None


def get_morph() -> pymorphy3.MorphAnalyzer:
    """Load the analyzer once (reads dictionaries from disk)."""
    global _MORPH  # noqa: PLW0603
    if _MORPH is None:
        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def is_russian(name: str) -> bool:
    return any("а" <= ch <= "я" or ch == "ё" for ch in name.lower())


def _nominative(morph, word: str, pos: tuple[str, ...]):
    for p in morph.parse(word):
        if p.tag.POS in pos and "nomn" in p.tag:
            return p
    return None


def _forms(name: str, numbers: tuple[str, ...]) -> dict[tuple[str, str], str]:
    """{(number, case): phrase} for a Russian name, lowercase."""
    morph = get_morph()
    words = name.split()
    head_len, animacy = len(words), "inan"
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in STOP_WORDS:
            head_len = i
            break
        noun = _nominative(morph, lw, ("NOUN",))
        if noun:
            animacy = noun.tag.animacy or "inan"
            # Non-nominative words after the head noun ("розетка чайника") stay unchanged.
            for j in range(i + 1, len(words)):
                if not _nominative(morph, words[j].lower(), ("NOUN", "ADJF", "PRTF")):
                    head_len = min(head_len, j)
                    break
            break

    result: dict[tuple[str, str], str] = {}
    for num in numbers:
        for case in CASES:
            out = []
            for i, w in enumerate(words):
                lw = w.lower()
                p = _nominative(morph, lw, ("NOUN", "ADJF", "PRTF")) if i < head_len else None
                if p is None:
                    out.append(lw)
                    continue
                grams = {case, num}
                if p.tag.POS != "NOUN" and case == "accs" and (num == "plur" or "masc" in p.tag):
                    grams.add(animacy)  # "настольные лампы", not "настольных лампы"
                form = p.inflect(grams) or p.inflect({case})
                out.append(form.word if form else lw)
            result[(num, case)] = " ".join(out)
    return result


def case_forms(name: str, plural: bool = True, exclude_cases: tuple[str, ...] = ()) -> set[str]:
    """All case forms of a Russian name (lowercase), excluding the name itself."""
    forms = _forms(name, ("sing", "plur") if plural else ("sing",))
    result = {phrase for (_num, case), phrase in forms.items() if case not in exclude_cases}
    result.discard(name.lower())
    return result


def inflect_phrase(name: str, case: str) -> str:
    """One singular case form: ("Список покупок", "loct") -> "списке покупок"."""
    return _forms(name, ("sing",))[("sing", case)]


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def match_item(spoken: str, items: list[str]) -> int | None:
    """Index of the list item the user meant: exact first, then any case form («колбасу»)."""
    target = _norm(spoken)
    for i, item in enumerate(items):
        if _norm(item) == target:
            return i
    for i, item in enumerate(items):
        if is_russian(item) and target in {_norm(f) for f in case_forms(item, plural=True)}:
            return i
    return None


def batch_case_forms(
    names: dict[str, str], plural: bool, exclude_cases: tuple[str, ...] = ()
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Inflect many names in one executor job: {key: name} -> ({key: forms}, {key: error})."""
    forms: dict[str, set[str]] = {}
    errors: dict[str, str] = {}
    for key, name in names.items():
        try:
            forms[key] = case_forms(name, plural, exclude_cases)
        except Exception as err:  # noqa: BLE001 - one odd name must not stop the others
            errors[key] = f"{type(err).__name__}: {err}"
    return forms, errors
