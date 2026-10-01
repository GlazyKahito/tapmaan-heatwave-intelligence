"""Spatio-temporal analysis: gridded maps, hotspots and region summaries.

* GridInterpolator  - inverse-distance-weighted (IDW) interpolation of station values onto
                      a 1-degree grid, the same resolution as IMD's gridded Tmax dataset.
* HotspotDetector   - Getis-Ord Gi* statistic, the standard GIS hotspot test. A station
                      whose neighbourhood is significantly hotter than the national
                      average (z > 1.96) is a hotspot.
* region_summary    - per-region aggregation for the seven IMD homogeneous regions.
"""

import math
from collections import defaultdict

from .config import ALERT_LEVELS, GRID_LAT, GRID_LON, GRID_STEP_DEG, HOTSPOT_BAND_KM, IDW_MAX_KM, IDW_POWER
from .science import haversine_km
from .stations_data import REGIONS


class GridInterpolator:
    def __init__(self, stations, step=GRID_STEP_DEG, power=IDW_POWER, max_km=IDW_MAX_KM):
        self.stations = list(stations)
        self.power, self.max_km = power, max_km
        self.cells = []      # (lat, lon)
        self._weights = []   # per cell: [(station_index, weight), ...]
        self.nearest = []    # per cell: index of the closest station
        lat = GRID_LAT[0]
        while lat <= GRID_LAT[1]:
            lon = GRID_LON[0]
            while lon <= GRID_LON[1]:
                pairs = []
                for i, st in enumerate(self.stations):
                    d = haversine_km(lat, lon, st.latitude, st.longitude)
                    if d <= self.max_km:
                        pairs.append((i, 1.0 / max(d, 1.0) ** self.power))
                if pairs:
                    self.cells.append((round(lat, 2), round(lon, 2)))
                    self._weights.append(pairs)
                    self.nearest.append(max(pairs, key=lambda p: p[1])[0])
                lon += step
            lat += step

    def cell_regions(self):
        return [self.stations[i].region for i in self.nearest]

    def interpolate(self, values):
        """values[i] belongs to self.stations[i]; None values are skipped."""
        out = []
        for pairs in self._weights:
            num = den = 0.0
            for i, w in pairs:
                if values[i] is not None:
                    num += w * values[i]
                    den += w
            out.append(round(num / den, 1) if den else None)
        return out


class HotspotDetector:
    """Getis-Ord Gi* with a fixed distance band (binary weights, self included)."""

    def __init__(self, stations, band_km=HOTSPOT_BAND_KM):
        self.stations = list(stations)
        self.neighbours = [[j for j, b in enumerate(self.stations)
                            if haversine_km(a.latitude, a.longitude, b.latitude, b.longitude) <= band_km]
                           for a in self.stations]

    def gi_star(self, values):
        pairs = [(i, v) for i, v in enumerate(values) if v is not None]
        n = len(pairs)
        if n < 3:
            return [None] * len(values)
        mean = sum(v for _, v in pairs) / n
        s = math.sqrt(sum(v * v for _, v in pairs) / n - mean * mean) or 1e-9
        valid = {i for i, _ in pairs}
        z = []
        for i, v in enumerate(values):
            if v is None:
                z.append(None)
                continue
            nb = [j for j in self.neighbours[i] if j in valid]
            wsum = len(nb)
            local = sum(values[j] for j in nb)
            denom = s * math.sqrt((n * wsum - wsum * wsum) / (n - 1)) if n > 1 else 0
            z.append(round((local - mean * wsum) / denom, 2) if denom > 0 else 0.0)
        return z

    @staticmethod
    def label(z):
        if z is None:
            return "n/a"
        if z >= 2.58:
            return "Hotspot (99%)"
        if z >= 1.96:
            return "Hotspot (95%)"
        if z <= -1.96:
            return "Coldspot (95%)"
        return "Not significant"


def region_summary(rows):
    """rows: station dicts produced by the engine. Groups by region with defaultdict."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["station"]["region"]].append(r)
    out = []
    for code, name in REGIONS.items():
        members = groups.get(code, [])
        if not members:
            continue
        tmaxes = [m["obs"]["tmax"] for m in members if m["obs"]["tmax"] is not None]
        anoms = [m["anomaly"] for m in members if m["anomaly"] is not None]
        hottest = max(members, key=lambda m: m["obs"]["tmax"] or -99)
        worst = max((m["alert"]["level"] for m in members), key=ALERT_LEVELS.index)
        out.append({
            "code": code, "name": name, "stations": len(members),
            "mean_tmax": round(sum(tmaxes) / len(tmaxes), 1) if tmaxes else None,
            "mean_anomaly": round(sum(anoms) / len(anoms), 1) if anoms else None,
            "max_tmax": hottest["obs"]["tmax"], "hottest": hottest["station"]["city"],
            "heatwave_stations": sum(1 for m in members if m["category"] != "NORMAL"),
            "worst_level": worst,
            "p_heatwave_72h": round(max(max(d["p_heatwave"] for d in m["forecast"][:3]) for m in members), 2),
        })
    return out
