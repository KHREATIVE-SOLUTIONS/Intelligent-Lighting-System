"""
Smart DMX Auto-Patching Service
================================

Handles automatic DMX address assignment, conflict detection, and
gap-finding across universes.
"""

import logging
from typing import List, Dict, Any, Set, Tuple, Optional

logger = logging.getLogger(__name__)

MAX_DMX_CHANNELS = 512
MAX_UNIVERSES = 16


class PatchConflict:
    """Represents a DMX address conflict between two fixtures."""

    def __init__(
        self,
        fixture_a_id: int,
        fixture_b_id: int,
        universe: int,
        overlap_start: int,
        overlap_end: int,
    ):
        self.fixture_a_id = fixture_a_id
        self.fixture_b_id = fixture_b_id
        self.universe = universe
        self.overlap_start = overlap_start
        self.overlap_end = overlap_end

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_a_id": self.fixture_a_id,
            "fixture_b_id": self.fixture_b_id,
            "universe": self.universe,
            "overlap_start": self.overlap_start,
            "overlap_end": self.overlap_end,
        }


class PatchingService:
    """Service for DMX address management and auto-patching."""

    @staticmethod
    def find_conflicts(
        fixtures: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Find DMX address conflicts among a list of rig fixtures.

        Each fixture dict must have: id, universe, dmx_address, channel_count.
        Returns list of conflict dicts.
        """
        conflicts = []

        # Group by universe
        by_universe: Dict[int, List[Dict[str, Any]]] = {}
        for f in fixtures:
            uni = f.get("universe", 0)
            by_universe.setdefault(uni, []).append(f)

        for universe, uni_fixtures in by_universe.items():
            # Sort by address
            sorted_fixtures = sorted(uni_fixtures, key=lambda x: x["dmx_address"])

            for i in range(len(sorted_fixtures)):
                a = sorted_fixtures[i]
                a_start = a["dmx_address"]
                a_end = a_start + a.get("channel_count", 1) - 1

                for j in range(i + 1, len(sorted_fixtures)):
                    b = sorted_fixtures[j]
                    b_start = b["dmx_address"]
                    b_end = b_start + b.get("channel_count", 1) - 1

                    # If b starts after a ends, no more overlaps possible
                    if b_start > a_end:
                        break

                    # Overlap detected
                    overlap_start = max(a_start, b_start)
                    overlap_end = min(a_end, b_end)
                    conflicts.append(
                        PatchConflict(
                            fixture_a_id=a["id"],
                            fixture_b_id=b["id"],
                            universe=universe,
                            overlap_start=overlap_start,
                            overlap_end=overlap_end,
                        ).to_dict()
                    )

        return conflicts

    @staticmethod
    def auto_patch(
        fixtures: List[Dict[str, Any]],
        locked_ids: Optional[Set[int]] = None,
    ) -> List[Dict[str, Any]]:
        """Auto-assign DMX addresses to unlocked fixtures.

        Assigns sequentially, respecting locked fixtures and universe
        boundaries (512 channels per universe).

        Each fixture dict must have: id, universe, dmx_address, channel_count.
        Optional: is_address_locked.

        Returns updated fixture list with new addresses.
        """
        if locked_ids is None:
            locked_ids = set()

        # Separate locked and unlocked
        locked = [f for f in fixtures if f["id"] in locked_ids or f.get("is_address_locked")]
        unlocked = [f for f in fixtures if f["id"] not in locked_ids and not f.get("is_address_locked")]

        # Build occupied ranges from locked fixtures per universe
        occupied: Dict[int, List[Tuple[int, int]]] = {}  # universe -> [(start, end)]
        for f in locked:
            uni = f.get("universe", 0)
            start = f["dmx_address"]
            end = start + f.get("channel_count", 1) - 1
            occupied.setdefault(uni, []).append((start, end))

        # Sort unlocked by their current address (preserve relative order)
        unlocked.sort(key=lambda x: (x.get("universe", 0), x["dmx_address"]))

        # Assign addresses
        current_universe = 0
        for f in unlocked:
            ch_count = f.get("channel_count", 1)
            placed = False

            for uni in range(current_universe, MAX_UNIVERSES):
                addr = PatchingService._find_next_available(
                    occupied.get(uni, []), ch_count
                )
                if addr is not None:
                    f["universe"] = uni
                    f["dmx_address"] = addr
                    occupied.setdefault(uni, []).append((addr, addr + ch_count - 1))
                    placed = True
                    current_universe = uni  # Don't go backwards
                    break

            if not placed:
                logger.warning(
                    f"Could not place fixture {f['id']} ({ch_count} channels) - "
                    f"all universes full"
                )

        return locked + unlocked

    @staticmethod
    def _find_next_available(
        occupied: List[Tuple[int, int]], channel_count: int
    ) -> Optional[int]:
        """Find the first available gap for a fixture with given channel count.

        Returns the 1-indexed DMX address, or None if no space in this universe.
        """
        if channel_count < 1 or channel_count > MAX_DMX_CHANNELS:
            return None

        # Sort occupied ranges
        sorted_ranges = sorted(occupied, key=lambda x: x[0])

        # Try to fit starting at address 1
        candidate = 1

        for start, end in sorted_ranges:
            if candidate + channel_count - 1 < start:
                # Gap found before this range
                return candidate
            # Move past this occupied range
            candidate = max(candidate, end + 1)

        # Check if there's room after the last occupied range
        if candidate + channel_count - 1 <= MAX_DMX_CHANNELS:
            return candidate

        return None

    @staticmethod
    def get_next_address(
        occupied: List[Tuple[int, int]], channel_count: int
    ) -> Optional[int]:
        """Public wrapper for finding the next available address."""
        return PatchingService._find_next_available(occupied, channel_count)
