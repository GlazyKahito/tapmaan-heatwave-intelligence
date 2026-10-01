"""Region-wise / seasonal analysis and national snapshot statistics.

* national_summary()   - Counter / defaultdict / sorted-with-key over the snapshot
* RegionalClimateAnalysis - 7 IMD regions x 4 seasons, trends (C/decade) and heatwave days
"""

from collections import Counter, defaultdict

from .climatology import Climatology
from .stations_data import REGIONS, SEASONS, STATIONS


# ------------------------------------------------------------------ snapshot statistics
def national_summary(rows):
    levels = Counter(r["alert"]["level"] for r in rows)
    categories = Counter(r["category"] for r in rows)
    by_state = defaultdict(list)
    for r in rows:
        by_state[r["station"]["state"]].append(r["obs"]["tmax"])
    valid = [r for r in rows if r["obs"]["tmax"] is not None]
    hottest = sorted(valid, key=lambda r: r["obs"]["tmax"], reverse=True)[:10]
    anomalous = sorted(valid, key=lambda r: r["anomaly"] or -99, reverse=True)[:10]
    temps = [r["obs"]["tmax"] for r in valid]
    return {
        "levels": {lvl: levels.get(lvl, 0) for lvl in ("GREEN", "YELLOW", "ORANGE", "RED")},
        "categories": dict(categories),
        "mean_tmax": round(sum(temps) / len(temps), 1) if temps else None,
        "max_tmax": max(temps) if temps else None,
        "max_heat_index": max((r["heat_index"] for r in valid), default=None),
        "hottest": [{"id": r["station"]["id"], "city": r["station"]["city"], "tmax": r["obs"]["tmax"]} for r in hottest],
        "most_anomalous": [{"id": r["station"]["id"], "city": r["station"]["city"], "anomaly": r["anomaly"]}
                           for r in anomalous],
        "hotspots": sum(1 for r in rows if (r["hotspot_z"] or 0) >= 1.96),
        "stations_by_state": {k: len(v) for k, v in sorted(by_state.items())},
    }


# ------------------------------------------------------------------ long-term analysis
def linear_trend(xs, ys):
    """Least-squares slope, returned per decade."""
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None]
    n = len(pts)
    if n < 3:
        return None
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    sxy = sum((x - mx) * (y - my) for x, y in pts)
    return round(sxy / sxx * 10, 2) if sxx else None


class RegionalClimateAnalysis:
    """Region-wise and seasonal analysis of the 30-year climatology (Phase II)."""

    def __init__(self, climatology=None):
        self.clim = climatology or Climatology.shared()
        self.region_of = {s[0]: s[5] for s in STATIONS}

    def _members(self, region):
        return [sid for sid, reg in self.region_of.items() if reg == region and sid in self.clim.stations]

    def season_table(self):
        """Mean Tmax for every region x season."""
        table = []
        for code, name in REGIONS.items():
            row = {"region": code, "name": name}
            for season, months in SEASONS.items():
                vals = [v for sid in self._members(code)
                        for year in self.clim.monthly_means(sid).values()
                        for m, v in enumerate(year, start=1) if m in months and v is not None]
                row[season] = round(sum(vals) / len(vals), 1) if vals else None
            table.append(row)
        return table

    def yearly_series(self):
        """Per region: pre-monsoon (MAM) mean Tmax and average heatwave days for each year."""
        out = []
        for code, name in REGIONS.items():
            members = self._members(code)
            if not members:
                continue
            years = sorted(self.clim.monthly_means(members[0]).keys())
            mam, hw = [], []
            for y in years:
                vals = [self.clim.monthly_means(s)[y][m - 1] for s in members for m in (3, 4, 5)
                        if self.clim.monthly_means(s).get(y) and self.clim.monthly_means(s)[y][m - 1] is not None]
                mam.append(round(sum(vals) / len(vals), 2) if vals else None)
                days = [self.clim.heatwave_days(s).get(y, 0) for s in members]
                hw.append(round(sum(days) / len(days), 2))
            xs = [int(y) for y in years]
            out.append({
                "region": code, "name": name, "years": xs, "mam_tmax": mam, "heatwave_days": hw,
                "mam_trend_per_decade": linear_trend(xs, mam),
                "hw_days_trend_per_decade": linear_trend(xs, hw),
            })
        return out

    def report(self):
        return {"available": self.clim.available, "source": self.clim.source, "period": self.clim.period,
                "seasons": {k: list(v) for k, v in SEASONS.items()},
                "season_table": self.season_table(), "series": self.yearly_series()}
