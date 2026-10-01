"""Long-term normals (Phase I output) and day-of-year lookups."""

import json
import math
import os
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def day_index(d):
    """0-based day-of-year index into a 365-long normal series (29 Feb -> 28 Feb)."""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return min(d.timetuple().tm_yday, 365) - 1


class Climatology:
    """Normal maximum temperature per station and day, plus yearly statistics."""

    _instance = None

    def __init__(self, path=os.path.join(DATA_DIR, "climatology.json")):
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            self.stations = payload["stations"]
            self.period = payload.get("period", ["?", "?"])
            self.source = payload.get("source", "unknown")
            self.available = True
        except (OSError, ValueError, KeyError):
            # Degrade gracefully: a smooth seasonal curve stands in for real normals.
            self.stations, self.period, self.source, self.available = {}, ["-", "-"], "fallback curve", False

    @classmethod
    def shared(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def normal_tmax(self, station_id, d, latitude=22.0):
        rec = self.stations.get(station_id)
        idx = day_index(d)
        if rec:
            return rec["normal_tmax_doy"][idx]
        # fallback: pre-monsoon peak around day 135, amplitude grows with latitude
        amp = 4 + 0.35 * max(latitude - 8, 0)
        return round(31 + amp * math.cos(2 * math.pi * (idx - 135) / 365) * 0.8, 2)

    def monthly_means(self, station_id):
        rec = self.stations.get(station_id, {})
        return rec.get("monthly_mean_tmax", {})

    def heatwave_days(self, station_id):
        rec = self.stations.get(station_id, {})
        return rec.get("heatwave_days", {})
