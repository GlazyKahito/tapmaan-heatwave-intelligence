"""Scenario Lab: what-if stress tests for the heatwave pipeline.

Each Scenario perturbs a *copy* of the station feeds (the real data is never touched),
then the engine re-runs forecasting, severity, hotspots and warnings on the result.
Operators can see how the system would react before such weather happens.

Scenario (ABC)
 |- HeatDome            blocking high over the north-west and central plains
 |- MonsoonOnset        rain and cloud cool the south and the coasts
 |- HumiditySurge       moist sea air drives humid heat along the coasts
 '- UrbanHeatIsland     megacities run hotter than their surroundings
"""

import copy
from abc import ABC, abstractmethod
from dataclasses import replace

METROS = {"WS101", "WS102", "WS103", "WS104", "WS105", "WS106", "WS107", "WS108", "WS109", "WS110"}


class Scenario(ABC):
    key = "base"
    title = "Scenario"
    icon = "•"
    summary = ""

    def apply(self, feeds):
        out = {}
        for sid, feed in feeds.items():
            new = copy.copy(feed)
            new.history_tmax = list(feed.history_tmax)
            new.observation = replace(feed.observation, notes=list(feed.observation.notes))
            if self.affects(feed.station):
                self.perturb(new)
                new.observation.notes.append(f"scenario: {self.title}")
            out[sid] = new
        return out

    @abstractmethod
    def affects(self, station):
        """True if this scenario changes the given station."""

    @abstractmethod
    def perturb(self, feed):
        """Modify the copied feed in place."""

    @staticmethod
    def _ramp(feed, deltas):
        """Add deltas to the last len(deltas) history days; today = last delta."""
        n = len(deltas)
        for k, d in enumerate(deltas):
            i = len(feed.history_tmax) - n + k
            if feed.history_tmax[i] is not None:
                feed.history_tmax[i] = round(feed.history_tmax[i] + d, 1)
        feed.observation.tmax = feed.history_tmax[-1]
        feed.observation.current_temp = feed.history_tmax[-1]

    def describe(self):
        return {"key": self.key, "title": self.title, "icon": self.icon, "summary": self.summary}


class HeatDome(Scenario):
    key, title, icon = "heat_dome", "Heat dome", "☀"
    summary = "A blocking high parks over North-West and Central India: +1 °C, +2 °C, then +3.5 °C over three days, drier air."

    def affects(self, station):
        return station.region in ("NW", "NC")

    def perturb(self, feed):
        self._ramp(feed, [1.0, 2.0, 3.5])
        if feed.observation.humidity is not None:
            feed.observation.humidity = max(4, feed.observation.humidity - 4)


class MonsoonOnset(Scenario):
    key, title, icon = "monsoon_onset", "Monsoon onset", "☂"
    summary = "Monsoon rain arrives over the south and both coasts: -2 °C yesterday and -4.5 °C today, humidity +30 %."

    def affects(self, station):
        return station.region in ("WC", "EC", "IP", "NE")

    def perturb(self, feed):
        self._ramp(feed, [-2.0, -4.5])
        if feed.observation.humidity is not None:
            feed.observation.humidity = min(95, feed.observation.humidity + 30)


class HumiditySurge(Scenario):
    key, title, icon = "humidity_surge", "Humidity surge", "≋"
    summary = "Moist sea air pushes inland on coastal and eastern stations: humidity +35 %, +1 °C. Watch the heat index and wet-bulb rules."

    def affects(self, station):
        return station.terrain == "coastal" or station.region == "EC"

    def perturb(self, feed):
        self._ramp(feed, [1.0])
        if feed.observation.humidity is not None:
            feed.observation.humidity = min(95, feed.observation.humidity + 35)


class UrbanHeatIsland(Scenario):
    key, title, icon = "urban_heat", "Urban heat island", "▦"
    summary = "The ten largest cities run 2.5 °C hotter than their surroundings for two weeks (concrete, traffic, little shade)."

    def affects(self, station):
        return station.station_id in METROS

    def perturb(self, feed):
        self._ramp(feed, [2.5] * len(feed.history_tmax))


SCENARIOS = {s.key: s for s in (HeatDome(), MonsoonOnset(), HumiditySurge(), UrbanHeatIsland())}
