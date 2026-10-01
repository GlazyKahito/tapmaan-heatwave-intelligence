"""HeatwaveIntelligence - the facade that runs the five-layer pipeline.

    1 Data acquisition   providers.py   (replay / live / simulated, resilient fallback)
    2 Analytics          spatial.py, analytics.py
    3 AI intelligence    forecast.py (Tmax + heatwave probability), alerts.py (severity),
                         spatial.HotspotDetector (Getis-Ord Gi*)
    4 Validation         validation.py (backtests), observed-vs-forecast per station
    5 Decision support   advisories.py (stakeholder advisories, channels, HITL)
"""

import threading
import time
from datetime import date, datetime

from . import science
from .advisories import TemplateAdvisoryGenerator, disseminate
from .alerts import EarlyWarningEngine, heatwave_streak
from .analytics import RegionalClimateAnalysis, national_summary
from .climatology import Climatology
from .config import ALERT_META, APP_NAME, APP_TAGLINE, FORECAST_HORIZON, LIVE_CACHE_SECONDS, USE_CASE_ID
from .exceptions import DataSourceError
from .forecast import fit_pooled, forecast_station
from .models import StationRegistry
from .providers import (IST, LiveProvider, ReplayProvider, ResilientProvider, SimulatedProvider,
                        describe_weather)
from .spatial import GridInterpolator, HotspotDetector, region_summary
from .stations_data import REGIONS, SEASONS
from .validation import ForecastValidator

MODES = ("replay", "live", "simulated")


class HeatwaveIntelligence:
    _shared = None

    def __init__(self):
        self.registry = StationRegistry()
        self.stations = list(self.registry)
        self.clim = Climatology.shared()
        self.replay = ReplayProvider()
        self.simulated = SimulatedProvider(self.clim)
        self.providers = {
            "replay": self.replay,
            "live": ResilientProvider(LiveProvider(), self.simulated),
            "simulated": self.simulated,
        }
        self.grid = GridInterpolator(self.stations)
        self.hotspots = HotspotDetector(self.stations)
        self.warning_engine = EarlyWarningEngine()
        self.advisor = TemplateAdvisoryGenerator()
        self.validator = ForecastValidator(self.registry, self.replay, self.clim)
        self.climate = RegionalClimateAnalysis(self.clim)
        self._cache, self._lock = {}, threading.Lock()

    @classmethod
    def shared(cls):
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    # ------------------------------------------------------------------ helpers
    def resolve(self, mode, date_str=None):
        mode = mode if mode in MODES else "replay"
        provider = self.providers[mode]
        if mode == "live":
            as_of = provider.default_date()  # live is always "today"
        else:
            try:
                as_of = date.fromisoformat(date_str) if date_str else provider.default_date()
            except ValueError:
                as_of = provider.default_date()
        if mode == "replay":
            lo, hi = self.replay.date_range
            as_of = min(max(as_of, date.fromisoformat(lo)), date.fromisoformat(hi))
        return mode, provider, as_of

    def meta(self):
        lo, hi = self.replay.date_range
        return {
            "app": APP_NAME, "tagline": APP_TAGLINE, "use_case": USE_CASE_ID,
            "modes": [{"id": m, "label": self.providers[m].label} for m in MODES],
            "replay_range": [lo, hi], "replay_default": self.replay.default_date().isoformat(),
            "regions": REGIONS, "seasons": {k: list(v) for k, v in SEASONS.items()},
            "alert_meta": ALERT_META, "horizon": FORECAST_HORIZON,
            "stations": [s.to_dict() for s in self.stations],
            "grid_cells": self.grid.cells,
            "climatology": {"source": self.clim.source, "period": self.clim.period, "available": self.clim.available},
        }

    # ------------------------------------------------------------------ pipeline
    def _analyse(self, feed, pooled=None):
        st, obs = feed.station, feed.observation
        normal = self.clim.normal_tmax(st.station_id, obs.date, st.latitude)
        tmax = obs.tmax
        anomaly = round(tmax - normal, 1) if tmax is not None else None
        category = st.classify(tmax, normal)
        rh = obs.humidity if obs.humidity is not None else 40
        hi = science.heat_index_c(tmax, rh) if tmax is not None else None
        tw = science.wet_bulb_c(tmax, rh) if tmax is not None else None
        forecast, model = forecast_station(st, feed, self.clim, pooled)
        streak = heatwave_streak(st, feed.history_dates, feed.history_tmax, self.clim)
        alert = self.warning_engine.assess(category, anomaly or 0.0, forecast, hi or 0, tw or 0, streak)
        obs_dict = obs.to_dict()
        obs_dict["condition"] = describe_weather(obs.weather_code)
        return {
            "station": st.to_dict(), "obs": obs_dict, "normal": round(normal, 1), "anomaly": anomaly,
            "category": category, "heat_index": hi, "hi_band": science.heat_index_band(hi or 0),
            "wet_bulb": tw, "streak": streak, "forecast": forecast, "model": model, "alert": alert,
            "future": {"kind": feed.future_kind, "dates": feed.future_dates, "tmax": feed.future_tmax},
            "hw_threshold": st.heatwave_threshold(normal),
        }

    def snapshot(self, mode="replay", date_str=None):
        mode, provider, as_of = self.resolve(mode, date_str)
        key = (mode, as_of.isoformat())
        with self._lock:
            hit = self._cache.get(key)
            if hit and (mode != "live" or time.time() - hit[0] < LIVE_CACHE_SECONDS):
                return hit[1]

        t0 = time.perf_counter()
        try:
            feeds = provider.fetch(self.registry, as_of)
            notes = list(getattr(provider, "notes", []))
        except DataSourceError as err:
            feeds, notes = self.simulated.fetch(self.registry, as_of), [f"{err}. Showing simulated data."]
        pooled = fit_pooled(feeds, self.clim)
        rows = [self._analyse(feeds[s.station_id], pooled) for s in self.stations]

        z = self.hotspots.gi_star([r["anomaly"] for r in rows])
        for r, zi in zip(rows, z):
            r["hotspot_z"], r["hotspot"] = zi, HotspotDetector.label(zi)

        fields = {"tmax_0": self.grid.interpolate([r["obs"]["tmax"] for r in rows]),
                  "anom_0": self.grid.interpolate([r["anomaly"] for r in rows])}
        for lead in range(1, FORECAST_HORIZON + 1):
            fields[f"tmax_{lead}"] = self.grid.interpolate([r["forecast"][lead - 1]["tmax"] for r in rows])
            fields[f"p_{lead}"] = self.grid.interpolate([r["forecast"][lead - 1]["p_heatwave"] for r in rows])
            fields[f"anom_{lead}"] = self.grid.interpolate(
                [round(r["forecast"][lead - 1]["tmax"] - r["forecast"][lead - 1]["normal"], 1) for r in rows])
        fields["p_0"] = self.grid.interpolate([1.0 if r["category"] != "NORMAL" else
                                               (0.5 if r["anomaly"] and r["anomaly"] > 2.5 else 0.0) for r in rows])

        snap = {
            "mode": mode, "source": provider.label, "as_of": as_of.isoformat(),
            "generated_at": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
            "notes": notes, "model": pooled.describe() if pooled else {"model": "Per-station fallback"},
            "stations": rows, "regions": region_summary(rows),
            "summary": national_summary(rows), "grid": fields,
            "compute_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        with self._lock:
            if len(self._cache) > 40:
                self._cache.clear()
            self._cache[key] = (time.time(), snap)
        return snap

    def station_detail(self, station_id, mode="replay", date_str=None):
        st = self.registry.get(station_id)
        snap = self.snapshot(mode, date_str)
        row = next(r for r in snap["stations"] if r["station"]["id"] == st.station_id)
        feed_dates, feed_tmax = self._history(st, snap)
        normals = [round(self.clim.normal_tmax(st.station_id, d, st.latitude), 1) for d in feed_dates]
        ctx = self.advisory_context(row)
        return {
            **row, "as_of": snap["as_of"], "mode": snap["mode"], "source": snap["source"],
            "history": {"dates": feed_dates, "tmax": feed_tmax, "normal": normals},
            "advisories": self.advisor.generate(ctx), "messages": disseminate(ctx),
        }

    def _history(self, st, snap):
        provider = self.providers[snap["mode"]]
        feeds = provider.fetch(self.registry, date.fromisoformat(snap["as_of"])) if snap["mode"] != "live" \
            else self.providers["live"].fetch(self.registry, date.fromisoformat(snap["as_of"]))
        feed = feeds[st.station_id]
        return feed.history_dates, feed.history_tmax

    @staticmethod
    def advisory_context(row):
        peak = max(row["forecast"], key=lambda d: d["tmax"])
        return {
            "station_id": row["station"]["id"], "city": row["station"]["city"], "state": row["station"]["state"],
            "date": row["obs"]["date"], "level": row["alert"]["level"], "tmax": row["obs"]["tmax"],
            "normal": row["normal"], "departure": row["anomaly"] or 0.0, "category": row["category"],
            "heat_index": row["heat_index"], "hi_band": row["hi_band"], "wet_bulb": row["wet_bulb"],
            "peak_tmax": peak["tmax"], "peak_date": peak["date"],
            "peak_day": date.fromisoformat(peak["date"]).strftime("%a %d %b"),
            "p_heatwave": max(d["p_heatwave"] for d in row["forecast"][:3]),
            "forecast": row["forecast"], "explanation": row["alert"]["explanation"],
        }

    def validation(self):
        return self.validator.run()

    def climate_analysis(self):
        return self.climate.report()
