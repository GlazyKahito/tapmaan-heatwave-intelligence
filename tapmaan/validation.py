"""Phase IV - Forecast validation (backtesting on the real 2024 heatwave).

For every station and every day from 1 May to 15 June 2024 the model is trained only on
the 14 days up to that date, then its 1-5 day forecasts are compared with what actually
happened. Two simple baselines keep the model honest:

* persistence - "tomorrow will be like today"
* climatology - "tomorrow will be normal"

Continuous scores: MAE, RMSE, bias, skill vs persistence.
Event scores (heatwave yes/no, forecast yes when probability >= 50 %):
POD (probability of detection), FAR (false alarm ratio), CSI (critical success index), Brier score.
"""

import math
from collections import defaultdict

from .climatology import Climatology
from .config import FORECAST_HISTORY_DAYS, FORECAST_HORIZON
from .forecast import fit_pooled, forecast_station
from .providers import StationFeed

BACKTEST_START, BACKTEST_END = "2024-05-01", "2024-06-15"


class ForecastValidator:
    def __init__(self, registry, replay, climatology=None):
        self.registry, self.replay = registry, replay
        self.clim = climatology or Climatology.shared()
        self._result = None

    def run(self):
        if self._result is not None:
            return self._result
        dates = self.replay.dates
        first = max(dates.index(BACKTEST_START), FORECAST_HISTORY_DAYS - 1)
        last = dates.index(BACKTEST_END)
        err = defaultdict(list)                  # (lead, kind) -> errors
        events = defaultdict(lambda: [0, 0, 0, 0])  # lead -> hits, misses, false alarms, correct negatives
        brier = defaultdict(list)
        region_err = defaultdict(list)

        for i in range(first, last + 1):
            hist_dates = dates[i - FORECAST_HISTORY_DAYS + 1:i + 1]
            feeds = {st.station_id: StationFeed(st, None, hist_dates,
                                                self.replay.data[st.station_id]["tmax"][i - FORECAST_HISTORY_DAYS + 1:i + 1])
                     for st in self.registry}
            pooled = fit_pooled(feeds, self.clim)  # trained only on data up to day i
            for st in self.registry:
                series = self.replay.data[st.station_id]["tmax"]
                days, _ = forecast_station(st, feeds[st.station_id], self.clim, pooled)
                today = series[i]
                for d in days:
                    j = i + d["lead"]
                    if j >= len(series) or series[j] is None or today is None:
                        continue
                    obs, lead = series[j], d["lead"]
                    err[(lead, "model")].append(d["tmax"] - obs)
                    err[(lead, "persistence")].append(today - obs)
                    err[(lead, "climatology")].append(d["normal"] - obs)
                    if lead == 1:
                        region_err[st.region].append(abs(d["tmax"] - obs))
                    observed_event = st.classify(obs, d["normal"]) != "NORMAL"
                    forecast_event = d["p_heatwave"] >= 0.5
                    cell = events[lead]
                    cell[0 if forecast_event and observed_event else
                         1 if observed_event else 2 if forecast_event else 3] += 1
                    brier[lead].append((d["p_heatwave"] - (1.0 if observed_event else 0.0)) ** 2)

        leads = []
        for lead in range(1, FORECAST_HORIZON + 1):
            row = {"lead": lead}
            for kind in ("model", "persistence", "climatology"):
                e = err[(lead, kind)]
                row[kind] = {"mae": round(sum(abs(x) for x in e) / len(e), 2),
                             "rmse": round(math.sqrt(sum(x * x for x in e) / len(e)), 2),
                             "bias": round(sum(e) / len(e), 2), "n": len(e)} if e else None
            if row["model"] and row["persistence"]:
                row["skill_vs_persistence"] = round(1 - row["model"]["mae"] / row["persistence"]["mae"], 3)
            h, m, f, c = events[lead]
            row["events"] = {
                "hits": h, "misses": m, "false_alarms": f, "correct_negatives": c,
                "pod": round(h / (h + m), 3) if h + m else None,
                "far": round(f / (h + f), 3) if h + f else None,
                "csi": round(h / (h + m + f), 3) if h + m + f else None,
                "brier": round(sum(brier[lead]) / len(brier[lead]), 4) if brier[lead] else None,
            }
            leads.append(row)
        self._result = {
            "period": [BACKTEST_START, BACKTEST_END], "stations": len(self.registry),
            "forecasts": sum(len(err[(l, "model")]) for l in range(1, FORECAST_HORIZON + 1)),
            "leads": leads,
            "region_mae_lead1": {k: round(sum(v) / len(v), 2) for k, v in sorted(region_err.items())},
        }
        return self._result
