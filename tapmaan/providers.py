"""Weather data providers (Phase I + III).

WeatherProvider (ABC)
 |- ReplayProvider     real ERA5 data of the April-June 2024 heatwave (bundled JSON)
 |- LiveProvider       today's data from the Open-Meteo forecast API, fetched with threads
 |- SimulatedProvider  offline synthetic weather built from the station normals
 '- ResilientProvider  composition: tries a primary provider, falls back per station

All providers return {station_id: StationFeed}; the rest of the system never needs to
know where the numbers came from (polymorphism).
"""

import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone

from .climatology import DATA_DIR, Climatology
from .config import FORECAST_HISTORY_DAYS, FORECAST_HORIZON, HTTP_TIMEOUT, LIVE_CACHE_SECONDS, LIVE_CHUNK_SIZE
from .exceptions import DataSourceError
from .models import DailyObservation

IST = timezone(timedelta(hours=5, minutes=30))

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 71: "Snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def describe_weather(code):
    return WMO_CODES.get(code, "Hot and hazy" if code is None else f"WMO code {code}")


def today_ist():
    return datetime.now(IST).date()


class StationFeed:
    """Everything one provider knows about one station for one 'as of' date."""

    def __init__(self, station, observation, history_dates, history_tmax,
                 future_dates=(), future_tmax=(), future_kind=None):
        self.station = station
        self.observation = observation
        self.history_dates = list(history_dates)  # ends with the as-of date
        self.history_tmax = list(history_tmax)
        self.future_dates = list(future_dates)
        self.future_tmax = list(future_tmax)
        self.future_kind = future_kind  # "observed" (replay) | "reference" (live) | None


class WeatherProvider(ABC):
    name = "abstract"
    label = "Abstract provider"

    @abstractmethod
    def fetch(self, registry, as_of):
        """Return {station_id: StationFeed} for every station in the registry."""

    def default_date(self):
        return today_ist()


class ReplayProvider(WeatherProvider):
    name = "replay"
    label = "Replay - real ERA5 data, April-June 2024 heatwave"

    def __init__(self, path=os.path.join(DATA_DIR, "replay_2024.json")):
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as err:
            raise DataSourceError(f"Replay dataset missing: {err}") from err
        self.dates = payload["dates"]
        self.data = payload["stations"]
        self.source = payload.get("source", "")

    @property
    def date_range(self):
        return self.dates[FORECAST_HISTORY_DAYS - 1], self.dates[-1]

    def default_date(self):
        return date.fromisoformat("2024-05-28")

    def fetch(self, registry, as_of):
        key = as_of.isoformat()
        if key not in self.dates:
            raise DataSourceError(f"Replay has data from {self.dates[0]} to {self.dates[-1]} only")
        i = self.dates.index(key)
        start = max(0, i - FORECAST_HISTORY_DAYS + 1)
        feeds = {}
        for st in registry:
            rec = self.data[st.station_id]
            obs = DailyObservation(
                st.station_id, key, rec["tmax"][i], rec["tmin"][i], rec["rh"][i], rec["wind"][i],
                rec["code"][i], rec["tmax"][i], source="replay (ERA5)")
            feeds[st.station_id] = StationFeed(
                st, obs, self.dates[start:i + 1], rec["tmax"][start:i + 1],
                self.dates[i + 1:i + 1 + FORECAST_HORIZON], rec["tmax"][i + 1:i + 1 + FORECAST_HORIZON],
                "observed")
        return feeds


class LiveProvider(WeatherProvider):
    """Open-Meteo forecast API. Stations are fetched in chunks, one thread per chunk."""

    name = "live"
    label = "Live - Open-Meteo forecast API (today)"
    URL = "https://api.open-meteo.com/v1/forecast"
    _cache = {}
    _cache_lock = threading.Lock()

    def _fetch_chunk(self, stations):
        params = {
            "latitude": ",".join(str(s.latitude) for s in stations),
            "longitude": ",".join(str(s.longitude) for s in stations),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_min,wind_speed_10m_max,weather_code",
            "past_days": FORECAST_HISTORY_DAYS - 1, "forecast_days": FORECAST_HORIZON + 1,
            "timezone": "Asia/Kolkata",
        }
        url = self.URL + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as err:
            raise DataSourceError(f"Open-Meteo request failed: {err}") from err
        if isinstance(payload, dict):
            payload = [payload]
        return payload

    def fetch(self, registry, as_of):
        key = as_of.isoformat()
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < LIVE_CACHE_SECONDS:
                return hit[1]

        stations = list(registry)
        chunks = [stations[i:i + LIVE_CHUNK_SIZE] for i in range(0, len(stations), LIVE_CHUNK_SIZE)]
        results, errors = {}, []
        lock = threading.Lock()

        def worker(chunk):
            try:
                payload = self._fetch_chunk(chunk)
                with lock:
                    for st, loc in zip(chunk, payload):
                        results[st.station_id] = self._to_feed(st, loc)
            except (DataSourceError, KeyError, IndexError, TypeError) as err:
                with lock:
                    errors.append(str(err))

        threads = [threading.Thread(target=worker, args=(c,), name=f"live-{n}") for n, c in enumerate(chunks)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if not results:
            raise DataSourceError("; ".join(errors) or "no data")
        with self._cache_lock:
            self._cache[key] = (time.time(), results)
        return results

    @staticmethod
    def _to_feed(st, loc):
        daily, cur = loc["daily"], loc.get("current", {})
        days = daily["time"]
        i = FORECAST_HISTORY_DAYS - 1  # index of today
        obs = DailyObservation(
            st.station_id, days[i], daily["temperature_2m_max"][i], daily["temperature_2m_min"][i],
            daily["relative_humidity_2m_min"][i], daily["wind_speed_10m_max"][i], daily["weather_code"][i],
            cur.get("temperature_2m"), source="live (Open-Meteo)")
        return StationFeed(st, obs, days[:i + 1], daily["temperature_2m_max"][:i + 1],
                           days[i + 1:], daily["temperature_2m_max"][i + 1:], "reference")


class SimulatedProvider(WeatherProvider):
    """Deterministic synthetic weather: normals + AR(1) anomalies + an optional heat dome."""

    name = "simulated"
    label = "Simulated - offline synthetic data from station normals"

    def __init__(self, climatology=None, heat_dome=True):
        self.clim = climatology or Climatology.shared()
        self.heat_dome = heat_dome

    def fetch(self, registry, as_of):
        feeds = {}
        days = [as_of - timedelta(days=k) for k in range(FORECAST_HISTORY_DAYS - 1, -FORECAST_HORIZON - 1, -1)]
        for st in registry:
            rng = random.Random(f"{st.station_id}-{as_of.isoformat()}")
            anomaly, series = rng.gauss(0, 1.5), []
            for n, d in enumerate(days):
                anomaly = 0.75 * anomaly + rng.gauss(0, 1.1)
                dome = 0.0
                if self.heat_dome and st.region in ("NW", "NC"):
                    dome = 4.0 * max(0.0, 1 - abs(n - FORECAST_HISTORY_DAYS + 2) / 7)
                normal = self.clim.normal_tmax(st.station_id, d, st.latitude)
                series.append(round(normal + anomaly + dome, 1))
            i = FORECAST_HISTORY_DAYS - 1
            tmax = series[i]
            rh = max(6, min(85, round(55 - (tmax - 30) * 2.4 + rng.gauss(0, 6) + (15 if st.terrain == "coastal" else 0))))
            obs = DailyObservation(st.station_id, as_of.isoformat(), tmax, round(tmax - rng.uniform(9, 14), 1),
                                   rh, round(rng.uniform(6, 24), 1), 0 if tmax > 38 else 2, tmax,
                                   source="simulated")
            feeds[st.station_id] = StationFeed(st, obs, [d.isoformat() for d in days[:i + 1]], series[:i + 1],
                                               [d.isoformat() for d in days[i + 1:]], series[i + 1:], "observed")
        return feeds


class ResilientProvider(WeatherProvider):
    """Tries the primary provider; any station it cannot serve comes from the fallback."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.name, self.label = primary.name, primary.label
        self.notes = []

    def default_date(self):
        return self.primary.default_date()

    def fetch(self, registry, as_of):
        self.notes = []
        try:
            feeds = dict(self.primary.fetch(registry, as_of))
        except DataSourceError as err:
            self.notes.append(f"{self.primary.label} unavailable ({err}). Using {self.fallback.label}.")
            feeds = {}
        missing = [s for s in registry if s.station_id not in feeds]
        if missing:
            backup = self.fallback.fetch(registry, as_of)
            for st in missing:
                feeds[st.station_id] = backup[st.station_id]
                backup[st.station_id].observation.notes.append("fallback: simulated data")
            if feeds and len(missing) < len(registry):
                self.notes.append(f"{len(missing)} station(s) filled with simulated data.")
        return feeds
