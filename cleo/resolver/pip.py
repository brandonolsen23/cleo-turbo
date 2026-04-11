"""
Point-in-polygon verification — local PIP tests against cached parcel geometries.

Two modes:
  1. Single PIP test: given a point and a polygon, check containment.
  2. Grid-indexed bulk PIP: load all cached parcels into a spatial grid,
     then test points against nearby parcels without any API calls.

The grid index is lazy-loaded and reusable across multiple calls.
"""

from __future__ import annotations

import json
import math
import os
from typing import Optional

from .cache import CACHE_DIR, cache_read_safe


# ── Ray-casting PIP ─────────────────────────────────────────────────

def point_in_polygon(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test.

    Args:
        lng, lat: Point coordinates (x=longitude, y=latitude).
        ring: List of [lng, lat] coordinate pairs forming a closed ring.

    Returns:
        True if the point is inside the polygon.
    """
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def pip_test_parcel(lat: float, lng: float, parcel: dict) -> bool:
    """Test if a point falls inside a cached parcel's geometry.

    Args:
        lat, lng: Point coordinates.
        parcel: Parcel dict from cache (has geometry.coordinates).

    Returns:
        True if point is inside the parcel polygon.
    """
    geom = parcel.get("geometry")
    if not geom:
        return False

    rings = geom.get("coordinates", [])
    if not rings or not rings[0]:
        return False

    return point_in_polygon(lng, lat, rings[0])


# ── Grid-indexed bulk PIP ───────────────────────────────────────────

# Grid cell size in degrees (~1.1 km at Ontario latitudes)
GRID_CELL_SIZE = 0.01


def _grid_key(lat: float, lng: float) -> tuple[int, int]:
    """Convert coordinates to grid cell key."""
    return (int(math.floor(lat / GRID_CELL_SIZE)),
            int(math.floor(lng / GRID_CELL_SIZE)))


class ParcelGrid:
    """Spatial grid index of cached parcel geometries.

    Loads all parcels from clean-data/parcels/ into a grid of ~1km cells.
    Each cell contains references to parcels whose bounding box intersects
    the cell. Point-in-polygon tests only check parcels in nearby cells.

    This enables local PIP verification with zero API calls.
    """

    def __init__(self):
        self._grid: dict[tuple[int, int], list[dict]] = {}
        self._loaded = False
        self._parcel_count = 0

    def load(self, verbose: bool = True) -> None:
        """Load all cached parcels into the grid index."""
        if self._loaded:
            return

        if verbose:
            print("  Loading parcel grid index...")

        count = 0
        for fname in os.listdir(CACHE_DIR):
            if not fname.endswith(".json"):
                continue

            parcel = cache_read_safe(fname.replace(".json", ""))
            if not parcel:
                continue

            geom = parcel.get("geometry")
            if not geom:
                continue

            rings = geom.get("coordinates", [])
            if not rings or not rings[0]:
                continue

            ring = rings[0]
            arn = parcel.get("arn", fname.replace(".json", ""))

            # Compute bounding box
            lngs = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            min_lat, max_lat = min(lats), max(lats)
            min_lng, max_lng = min(lngs), max(lngs)

            # Insert into all grid cells that the bbox touches
            entry = {"arn": arn, "ring": ring}
            lat_lo = int(math.floor(min_lat / GRID_CELL_SIZE))
            lat_hi = int(math.floor(max_lat / GRID_CELL_SIZE))
            lng_lo = int(math.floor(min_lng / GRID_CELL_SIZE))
            lng_hi = int(math.floor(max_lng / GRID_CELL_SIZE))

            for lat_cell in range(lat_lo, lat_hi + 1):
                for lng_cell in range(lng_lo, lng_hi + 1):
                    key = (lat_cell, lng_cell)
                    if key not in self._grid:
                        self._grid[key] = []
                    self._grid[key].append(entry)

            count += 1

        self._parcel_count = count
        self._loaded = True

        if verbose:
            print(f"  Grid loaded: {count:,} parcels in {len(self._grid):,} cells")

    def find_containing_parcel(self, lat: float, lng: float) -> Optional[str]:
        """Find the ARN of the parcel containing this point.

        Args:
            lat, lng: Point coordinates.

        Returns:
            ARN string if a containing parcel is found, None otherwise.
        """
        if not self._loaded:
            self.load()

        key = _grid_key(lat, lng)

        # Check the cell and immediate neighbors (handles edge cases)
        for dlat in (-1, 0, 1):
            for dlng in (-1, 0, 1):
                neighbor = (key[0] + dlat, key[1] + dlng)
                entries = self._grid.get(neighbor, [])
                for entry in entries:
                    if point_in_polygon(lng, lat, entry["ring"]):
                        return entry["arn"]

        return None

    @property
    def parcel_count(self) -> int:
        return self._parcel_count


# Module-level grid instance (lazy loaded)
_grid: Optional[ParcelGrid] = None


def get_grid() -> ParcelGrid:
    """Get or create the module-level parcel grid."""
    global _grid
    if _grid is None:
        _grid = ParcelGrid()
    return _grid


def verify_pip(lat: float, lng: float, expected_arn: str) -> bool:
    """Verify that coordinates fall inside the expected parcel.

    First tries a direct PIP test against the cached parcel geometry.
    If that fails, falls back to the grid index to see if the point
    is inside a different parcel.

    Args:
        lat, lng: Coordinates to test.
        expected_arn: The ARN the record was resolved to.

    Returns:
        True if the point is inside the expected parcel.
    """
    # Direct test against the expected parcel
    parcel = cache_read_safe(expected_arn)
    if parcel and pip_test_parcel(lat, lng, parcel):
        return True

    return False


def find_correct_parcel(lat: float, lng: float) -> Optional[str]:
    """Find which parcel actually contains these coordinates.

    Uses the grid index for zero-API-call lookup.

    Args:
        lat, lng: Coordinates to test.

    Returns:
        ARN of the containing parcel, or None.
    """
    grid = get_grid()
    grid.load(verbose=False)
    return grid.find_containing_parcel(lat, lng)
