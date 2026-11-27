"""
Matching a file's fixture types to the library
==============================================

A file names a fixture type in words. The library holds profiles. Only an exact
match of the normalised name is applied without asking: the same maker and
model, or a model name only one library profile has. Anything looser is offered
as a suggestion under "unmatched", because patching a rig on a profile that is
merely similar drives the wrong channels on real fixtures.

A library entry here is a plain dict, so all of this runs without a database:

    {"id", "manufacturer", "model", "fixture_type", "gdtf_id", "source",
     "modes": [{"id", "name", "channel_count"}]}
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Profiles this importer writes for a type it could not match. Never a match
# for anything: they describe a footprint, not a fixture.
PLACEHOLDER_SOURCE = "import_placeholder"

MAX_SUGGESTIONS = 3

_GENERIC_WORDS = {"led", "dmx", "rgb", "rgbw", "the", "and", "mk", "ii", "pro", "generic"}


def normalise(text: str) -> str:
    """Letters and digits only, lower case: "MAC Aura-XB" and "mac aura xb" are one."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _words(text: str) -> set:
    return {
        word for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(word) > 1 and word not in _GENERIC_WORDS
    }


def _full_name(entry: Dict[str, Any]) -> str:
    return f"{entry.get('manufacturer') or ''} {entry.get('model') or ''}".strip()


def _best(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Of several identical library rows, one that has modes, then the oldest."""
    return sorted(entries, key=lambda e: (0 if e.get("modes") else 1, e.get("id") or 0))[0]


def match_type(
    type_name: str,
    manufacturer: str,
    model: str,
    library: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], str, List[Dict[str, Any]]]:
    """(the library profile, how it matched, suggestions when it did not).

    How is "name" (maker and model both agree) or "model" (the model name
    belongs to exactly one profile). No match returns (None, "", suggestions).
    """
    candidates = [e for e in library if e.get("source") != PLACEHOLDER_SOURCE]
    wanted_full = normalise(type_name) or normalise(f"{manufacturer} {model}")
    wanted_model = normalise(model)
    if not wanted_full and not wanted_model:
        return None, "", []

    by_full = [e for e in candidates if wanted_full and normalise(_full_name(e)) == wanted_full]
    if by_full:
        return _best(by_full), "name", []

    for wanted in (wanted_model, wanted_full):
        if not wanted:
            continue
        by_model = [e for e in candidates if normalise(e.get("model") or "") == wanted]
        makers = {normalise(e.get("manufacturer") or "") for e in by_model}
        if by_model and len(makers) == 1:
            return _best(by_model), "model", []

    return None, "", suggest(type_name or f"{manufacturer} {model}", candidates)


def suggest(type_name: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Library profiles that look related. For a person to choose from, never applied."""
    wanted = normalise(type_name)
    wanted_words = _words(type_name)
    scored = []
    for entry in candidates:
        full = normalise(_full_name(entry))
        model = normalise(entry.get("model") or "")
        score = 0.0
        if len(model) >= 4 and model in wanted:
            score = 3.0
        elif len(wanted) >= 4 and wanted in full:
            score = 2.5
        else:
            shared = wanted_words & _words(_full_name(entry))
            if len(shared) >= 2:
                score = len(shared) / max(len(wanted_words), 1)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].get("id") or 0))
    return [
        {
            "fixture_id": entry.get("id"),
            "manufacturer": entry.get("manufacturer"),
            "model": entry.get("model"),
            "fixture_type": entry.get("fixture_type"),
        }
        for _, entry in scored[:MAX_SUGGESTIONS]
    ]


def pick_mode(
    modes: List[Dict[str, Any]],
    mode_name: str,
    channel_count: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """(the mode a fixture is patched in, how it was chosen).

    How is one of:
      "name"      the file names it
      "footprint" the file states a channel count only one mode has
      "only"      the profile has one mode
      "guessed"   none of the above; the first mode, which is also what the rig
                  loader falls back to. Reported, because a wrong mode moves
                  every channel after the first difference.
      ""          the profile has no modes
    """
    if not modes:
        return None, ""
    wanted = normalise(mode_name)
    if wanted:
        for mode in modes:
            if normalise(mode.get("name") or "") == wanted:
                return mode, "name"
    if channel_count:
        same = [m for m in modes if int(m.get("channel_count") or 0) == int(channel_count)]
        if len(same) == 1:
            return same[0], "footprint"
    if len(modes) == 1:
        return modes[0], "only"
    ordered = sorted(modes, key=lambda m: (m.get("id") is None, m.get("id") or 0))
    return ordered[0], "guessed"
