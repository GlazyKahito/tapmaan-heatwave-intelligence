"""Phase III - IoT Automated Weather Station (AWS) network simulator.

Three sensor monitors poll the AWS nodes *concurrently*, one thread per parameter:
temperature, humidity and wind speed.

    SensorMonitor(threading.Thread)          base class, overrides run()
     |- TemperatureMonitor                   polymorphic read() / valid range
     |- HumidityMonitor
     '- WindSpeedMonitor

Each read waits on simulated radio latency (I/O-bound, so threads really overlap) and
may fail on purpose: communication timeouts, missing data or impossible values. Every
failure raises a custom exception that is caught, logged and turned into a status, so
one bad sensor never stops the sweep (try / except / else / finally).
"""

import random
import threading
import time

from .exceptions import (InvalidSensorValueError, SensorCommunicationError, SensorError,
                         WeatherDataUnavailableError)

THRESHOLDS = {"temperature": 40.0, "humidity": 70.0, "wind": 40.0}


class SensorMonitor(threading.Thread):
    parameter, unit = "generic", ""
    valid_range = (float("-inf"), float("inf"))

    def __init__(self, network, stations, truth):
        super().__init__(name=f"{self.parameter}-monitor", daemon=True)
        self.network = network
        self.stations = stations
        self.truth = truth  # {station_id: value from the current observation}
        self.rng = random.Random(f"{network.seed}-{self.parameter}")

    # ---- polymorphic hooks -------------------------------------------------------
    def read(self, station_id):
        """Simulate one radio round-trip to the AWS node and return the raw value."""
        latency = self.rng.uniform(0.012, 0.035)
        fault = self.rng.random()
        if fault < self.network.fault_rate * 0.35:
            time.sleep(latency * 2)
            raise SensorCommunicationError(station_id, self.parameter, "node did not respond (timeout)")
        time.sleep(latency)
        if fault < self.network.fault_rate * 0.65:
            raise WeatherDataUnavailableError(station_id, self.parameter, "no data in packet")
        if fault < self.network.fault_rate:
            return self.corrupt_value()
        base = self.truth.get(station_id)
        if base is None:
            raise WeatherDataUnavailableError(station_id, self.parameter, "no observation available")
        return round(base + self.rng.gauss(0, self.noise()), 1)

    def noise(self):
        return 0.3

    def corrupt_value(self):
        return 999.9

    def validate(self, station_id, value):
        lo, hi = self.valid_range
        if not lo <= value <= hi:
            raise InvalidSensorValueError(station_id, self.parameter,
                                          f"value {value} {self.unit} outside {lo}..{hi}")
        return value

    # ---- thread body -------------------------------------------------------------
    def run(self):
        for sid in self.stations:
            start = time.perf_counter()
            status, value, message = "ok", None, ""
            try:
                raw = self.read(sid)
                value = self.validate(sid, raw)
            except SensorCommunicationError as err:
                status, message = "comm_failure", str(err)
            except WeatherDataUnavailableError as err:
                status, message = "missing", str(err)
            except InvalidSensorValueError as err:
                status, message = "invalid", str(err)
            except SensorError as err:  # any other sensor problem
                status, message = "error", str(err)
            else:
                if value > THRESHOLDS[self.parameter]:
                    message = f"threshold {THRESHOLDS[self.parameter]} {self.unit} exceeded"
            finally:
                self.network.record(self.parameter, sid, start, time.perf_counter(), status, value, message)


class TemperatureMonitor(SensorMonitor):
    parameter, unit, valid_range = "temperature", "°C", (-10.0, 55.0)

    def corrupt_value(self):
        return self.rng.choice([85.3, -40.0, 999.9])


class HumidityMonitor(SensorMonitor):
    parameter, unit, valid_range = "humidity", "%", (0.0, 100.0)

    def noise(self):
        return 2.0

    def corrupt_value(self):
        return self.rng.choice([137.0, -3.0])


class WindSpeedMonitor(SensorMonitor):
    parameter, unit, valid_range = "wind", "km/h", (0.0, 150.0)

    def noise(self):
        return 1.5

    def corrupt_value(self):
        return self.rng.choice([-5.0, 412.0])


class AWSNetwork:
    """Runs a concurrent sweep and collects a thread-safe event log."""

    MONITORS = (TemperatureMonitor, HumidityMonitor, WindSpeedMonitor)

    def __init__(self, fault_rate=0.12, seed=None):
        if not 0 <= fault_rate <= 0.9:
            raise ValueError("fault_rate must be between 0 and 0.9")
        self.fault_rate = fault_rate
        self.seed = seed if seed is not None else random.randrange(1_000_000)
        self._lock = threading.Lock()
        self._events = []
        self._t0 = 0.0

    def record(self, parameter, sid, start, end, status, value, message):
        with self._lock:  # many threads append to one list -> protect it
            self._events.append({
                "thread": parameter, "station_id": sid, "status": status, "value": value,
                "message": message, "start_ms": round((start - self._t0) * 1000, 2),
                "end_ms": round((end - self._t0) * 1000, 2),
            })

    def sweep(self, observations):
        """observations: {station_id: DailyObservation}. Returns the sweep report dict."""
        sids = sorted(observations)
        truth = {
            "temperature": {s: observations[s].tmax for s in sids},
            "humidity": {s: observations[s].humidity for s in sids},
            "wind": {s: observations[s].wind for s in sids},
        }
        self._events, self._t0 = [], time.perf_counter()
        threads = [cls(self, sids, truth[cls.parameter]) for cls in self.MONITORS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        wall = (time.perf_counter() - self._t0) * 1000
        busy = sum(e["end_ms"] - e["start_ms"] for e in self._events)
        return {
            "seed": self.seed, "fault_rate": self.fault_rate, "stations": sids,
            "events": sorted(self._events, key=lambda e: e["start_ms"]),
            "wall_ms": round(wall, 1), "sequential_ms": round(busy, 1),
            "speedup": round(busy / wall, 2) if wall else None,
            "warnings": self.threshold_warnings(),
            "counts": self.status_counts(),
        }

    def status_counts(self):
        counts = {}
        for e in self._events:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        return counts

    def threshold_warnings(self):
        latest = {}
        for e in self._events:
            if e["status"] == "ok":
                latest.setdefault(e["station_id"], {})[e["thread"]] = e["value"]
        warnings = []
        for sid, vals in sorted(latest.items()):
            t, h, w = vals.get("temperature"), vals.get("humidity"), vals.get("wind")
            if t is not None and t >= 45:
                warnings.append({"station_id": sid, "level": "CRITICAL", "text": f"Extreme heat {t} °C"})
            elif t is not None and t >= THRESHOLDS["temperature"]:
                warnings.append({"station_id": sid, "level": "WARNING", "text": f"Heatwave-level temperature {t} °C"})
            if t is not None and h is not None and t >= 35 and h >= THRESHOLDS["humidity"]:
                warnings.append({"station_id": sid, "level": "WARNING", "text": f"Humid heat: {t} °C at {h} % RH"})
            if w is not None and w >= THRESHOLDS["wind"]:
                warnings.append({"station_id": sid, "level": "WARNING", "text": f"Strong hot winds {w} km/h"})
        return warnings
