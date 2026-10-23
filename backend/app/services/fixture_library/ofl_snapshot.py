"""
Offline Open Fixture Library
============================

The Open Fixture Library (OFL) is the default source for fixture profiles: it is
MIT licensed, plain JSON, and covers the brands a club rig is built from (Chauvet
DJ, ADJ, Martin, Robe, Elation, Cameo, Showtec and more). A venue patches at
load-in, often before the house network is up, so the whole library ships with
the app as one gzipped snapshot (data/fixtures/ofl/ofl_snapshot.json.gz, rebuilt
by scripts/update_ofl_snapshot.py). The online OFL is only consulted for a key
the snapshot does not hold.

Search here is what the fixture picker drives: "rogue r2", "adj mega par",
"intimidator 260" all find the fixture, and every hit already says which mode we
would patch and what that mode can do, so the operator rarely has to open the
manual.
"""

import gzip
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.fixture_library.ofl_client import convert_ofl_to_internal
from app.services.rig.fixture_choice import mode_features, recommend_mode

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "fixtures" / "ofl" / "ofl_snapshot.json.gz"
)

# Names people say that OFL does not use. "ADJ" is how every tech says American DJ.
MANUFACTURER_ALIASES = {
    "american-dj": "adj",
    "chauvet-professional": "chauvet pro",
}

_MAX_REDIRECTS = 4
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall(str(text or "").lower())


def _compact(text: str) -> str:
    return "".join(_tokens(text))


class OFLSnapshot:
    """The bundled OFL copy, loaded on first use."""

    def __init__(self, path: Path = DEFAULT_SNAPSHOT_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: Optional[Dict[str, Any]] = None
        self._entries: Optional[List[Dict[str, Any]]] = None
        self._haystacks: Dict[str, Dict[str, Any]] = {}

    # -- loading ---------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        if self._data is not None:
            return self._data
        with self._lock:
            if self._data is None:
                try:
                    with gzip.open(self.path, "rt", encoding="utf-8") as fh:
                        data = json.load(fh)
                except FileNotFoundError:
                    logger.warning("No offline fixture library at %s", self.path)
                    data = {}
                except (OSError, ValueError) as e:
                    logger.error("Offline fixture library at %s is unreadable: %s", self.path, e)
                    data = {}
                data.setdefault("fixtures", {})
                data.setdefault("manufacturers", {})
                data.setdefault("redirects", {})
                self._data = data
        return self._data

    @property
    def available(self) -> bool:
        return bool(self._load()["fixtures"])

    def info(self) -> Dict[str, Any]:
        data = self._load()
        return {
            "available": bool(data["fixtures"]),
            "fixture_count": len(data["fixtures"]),
            "manufacturer_count": len(data["manufacturers"]),
            "commit": data.get("commit"),
            "generated": data.get("generated"),
        }

    # -- lookups ---------------------------------------------------------

    def manufacturer_name(self, manufacturer_key: str) -> Optional[str]:
        entry = self._load()["manufacturers"].get(manufacturer_key)
        return entry.get("name") if isinstance(entry, dict) else None

    def resolve_key(self, manufacturer_key: str, fixture_key: str) -> str:
        """The current key for a fixture, following OFL's rename redirects."""
        data = self._load()
        key = f"{manufacturer_key}/{fixture_key}"
        for _ in range(_MAX_REDIRECTS):
            target = data["redirects"].get(key)
            if not target:
                break
            key = target
        return key

    def get(self, manufacturer_key: str, fixture_key: str) -> Optional[Dict[str, Any]]:
        """The raw OFL definition, or None when the snapshot does not hold it."""
        key = self.resolve_key(manufacturer_key, fixture_key)
        return self._load()["fixtures"].get(key)

    def convert(self, manufacturer_key: str, fixture_key: str) -> Optional[Dict[str, Any]]:
        """The definition converted to our profile format, with real names."""
        key = self.resolve_key(manufacturer_key, fixture_key)
        definition = self._load()["fixtures"].get(key)
        if definition is None:
            return None
        mfr_key, _, fix_key = key.partition("/")
        return convert_ofl_to_internal(
            definition, mfr_key, fix_key, manufacturer_name=self.manufacturer_name(mfr_key)
        )

    # -- search ----------------------------------------------------------

    def entries(self) -> List[Dict[str, Any]]:
        """One summary per fixture, built once: type, modes and the mode we'd pick."""
        if self._entries is not None:
            return self._entries
        data = self._load()
        entries = []
        for key in sorted(data["fixtures"]):
            mfr_key, _, fix_key = key.partition("/")
            try:
                converted = self.convert(mfr_key, fix_key)
            except Exception as e:  # one bad definition must not hide the library
                logger.warning("Skipping OFL fixture %s: %s", key, e)
                continue
            if not converted:
                continue
            entries.append(summarise(converted, key))
            definition = data["fixtures"][key]
            aliases = MANUFACTURER_ALIASES.get(mfr_key, "")
            text = " ".join([
                converted["manufacturer"], mfr_key.replace("-", " "), aliases,
                converted["model"], fix_key.replace("-", " "),
                str(definition.get("shortName") or ""),
            ])
            self._haystacks[key] = {
                "tokens": set(_tokens(text)),
                "compact": _compact(text),
                "manufacturer": set(_tokens(f"{converted['manufacturer']} {mfr_key} {aliases}")),
            }
        self._entries = entries
        return entries

    def search(
        self,
        query: str = "",
        fixture_type: Optional[str] = None,
        manufacturer: Optional[str] = None,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """Fixtures matching every word of the query, best match first."""
        words = _tokens(query)
        hits = []
        for entry in self.entries():
            if fixture_type and entry["fixture_type"] != fixture_type:
                continue
            if manufacturer and entry["manufacturer_key"] != manufacturer:
                continue
            score = self._score(entry["key"], words)
            if score is None:
                continue
            hits.append((score, entry))
        hits.sort(key=lambda hit: (-hit[0], hit[1]["manufacturer"].lower(), hit[1]["name"].lower()))
        return [entry for _, entry in hits[:limit]]

    def _score(self, key: str, words: List[str]) -> Optional[int]:
        if not words:
            return 0
        haystack = self._haystacks.get(key)
        if haystack is None:
            return None
        total = 0
        for word in words:
            if word in haystack["tokens"]:
                points = 3
            elif any(token.startswith(word) for token in haystack["tokens"]):
                points = 2
            elif word in haystack["compact"]:
                points = 1
            else:
                return None
            if any(token.startswith(word) for token in haystack["manufacturer"]):
                points += 1
            total += points
        return total


def summarise(converted: Dict[str, Any], key: str) -> Dict[str, Any]:
    """What the picker shows for one fixture, from a converted definition."""
    modes = converted.get("modes") or []
    recommended = recommend_mode(modes)
    mfr_key, _, fix_key = key.partition("/")
    return {
        "key": key,
        "manufacturer_key": mfr_key,
        "fixture_key": fix_key,
        "manufacturer": converted["manufacturer"],
        "name": converted["model"],
        "fixture_type": converted.get("fixture_type", "other"),
        "categories": converted.get("categories") or [],
        "modes": [
            {
                "name": m["name"],
                "channel_count": m["channel_count"],
                "features": mode_features(m),
                "recommended": m is recommended,
            }
            for m in modes
        ],
        "recommended_mode": recommended["name"] if recommended else None,
        "source": "ofl",
    }


_snapshot: Optional[OFLSnapshot] = None


def get_snapshot() -> OFLSnapshot:
    global _snapshot
    if _snapshot is None:
        _snapshot = OFLSnapshot()
    return _snapshot
