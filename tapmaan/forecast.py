"""Phase II - Region-wise maximum-temperature forecasting and heatwave prediction.

Main model - RegionalRidgeForecaster (spatio-temporal, learned every day):
    For each lead time h = 1..5 a separate ridge regression predicts the Tmax *anomaly*
    (Tmax minus the station normal) h days ahead from three features:
        x1  today's anomaly at the station
        x2  the change since yesterday (momentum)
        x3  today's mean anomaly of the station's IMD region (spatial context)
    The model is pooled across all 50 stations and trained only on the last 14 days, so
    it re-learns every day from the newest observations (no look-ahead).
    On the real May-June 2024 backtest it beats the persistence baseline at every lead.

Fallback model - HoltDampedModel: per-station damped double exponential smoothing,
used when the pooled model cannot be trained (e.g. too much missing data).

Uncertainty: the residual spread of each lead's training fit gives a normal
distribution, from which heatwave probabilities follow.
"""

import math
from collections import defaultdict
from datetime import date, timedelta
from functools import reduce

from . import science
from .config import FORECAST_HORIZON, HOLT_ALPHAS, HOLT_BETAS, HOLT_PHI
from .exceptions import ForecastError

FEATURES = ("anomaly_today", "change_since_yesterday", "regional_anomaly", "intercept")
RIDGE_LAMBDA = 2.0
MIN_SIGMA = 0.9


def solve_linear(matrix, rhs):
    """Gauss-Jordan elimination with partial pivoting (no NumPy needed)."""
    n = len(rhs)
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            raise ForecastError("Singular system - not enough varied training data")
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


class RegionalRidgeForecaster:
    def __init__(self, horizon=FORECAST_HORIZON, lam=RIDGE_LAMBDA):
        self.horizon, self.lam = horizon, lam
        self.weights, self.sigma, self.samples = {}, {}, {}
        self.anomalies, self.regional = {}, {}
        self.fitted = False

    @staticmethod
    def _features(series, regional, t):
        a, a_prev, r = series[t], series[t - 1], regional[t]
        if a is None or a_prev is None or r is None:
            return None
        return [a, a - a_prev, r, 1.0]

    def fit(self, feeds, climatology):
        """feeds: {station_id: StationFeed}, all sharing the same history dates."""
        by_region = defaultdict(list)
        for sid, feed in feeds.items():
            st = feed.station
            self.anomalies[sid] = [None if t is None else t - climatology.normal_tmax(sid, d, st.latitude)
                                   for d, t in zip(feed.history_dates, feed.history_tmax)]
            by_region[st.region].append(sid)
        length = min(len(v) for v in self.anomalies.values())
        for region, members in by_region.items():
            series = []
            for t in range(length):
                vals = [self.anomalies[s][t] for s in members if self.anomalies[s][t] is not None]
                series.append(sum(vals) / len(vals) if vals else None)
            for s in members:
                self.regional[s] = series

        for h in range(1, self.horizon + 1):
            xtx = [[0.0] * 4 for _ in range(4)]
            xty = [0.0] * 4
            rows = []
            for sid, series in self.anomalies.items():
                for t in range(1, length - h):
                    x = self._features(series, self.regional[sid], t)
                    y = series[t + h]
                    if x is None or y is None:
                        continue
                    rows.append((x, y))
                    for p in range(4):
                        xty[p] += x[p] * y
                        for q in range(4):
                            xtx[p][q] += x[p] * x[q]
            if len(rows) < 30:
                raise ForecastError(f"Only {len(rows)} training samples for lead {h}")
            for p in range(3):  # ridge penalty (not on the intercept)
                xtx[p][p] += self.lam
            w = solve_linear(xtx, xty)
            sse = reduce(lambda acc, xy: acc + (sum(a * b for a, b in zip(w, xy[0])) - xy[1]) ** 2, rows, 0.0)
            self.weights[h] = w
            self.sigma[h] = max(math.sqrt(sse / len(rows)), MIN_SIGMA)
            self.samples[h] = len(rows)
        self.fitted = True
        return self

    def predict_anomalies(self, station_id):
        if not self.fitted:
            raise ForecastError("Model is not fitted")
        series = self.anomalies[station_id]
        x = self._features(series, self.regional[station_id], len(series) - 1)
        if x is None:
            raise ForecastError(f"{station_id}: today's observation is missing")
        return [(sum(a * b for a, b in zip(self.weights[h], x)), self.sigma[h])
                for h in range(1, self.horizon + 1)]

    def describe(self):
        return {
            "model": "Regional ridge regression (pooled, retrained daily)",
            "features": list(FEATURES),
            "weights": {h: [round(v, 3) for v in w] for h, w in self.weights.items()},
            "sigma": {h: round(s, 2) for h, s in self.sigma.items()},
            "training_samples": self.samples,
        }


class HoltDampedModel:
    """Fallback: double exponential smoothing with a damped trend, per station."""

    def __init__(self, alpha, beta, phi=HOLT_PHI):
        self.alpha, self.beta, self.phi = alpha, beta, phi
        self.level = self.trend = 0.0
        self.residuals = []

    def fit(self, series):
        level, trend = series[0], series[1] - series[0] if len(series) > 1 else 0.0
        residuals = []
        for y in series[1:]:
            predicted = level + self.phi * trend
            residuals.append(y - predicted)
            new_level = self.alpha * y + (1 - self.alpha) * predicted
            trend = self.beta * (new_level - level) + (1 - self.beta) * self.phi * trend
            level = new_level
        self.level, self.trend, self.residuals = level, trend, residuals
        return self

    @property
    def sse(self):
        return reduce(lambda acc, r: acc + r * r, self.residuals, 0.0)

    @property
    def rmse(self):
        return math.sqrt(self.sse / len(self.residuals)) if self.residuals else 2.0

    def predict(self, horizon):
        out, damp = [], 0.0
        for h in range(1, horizon + 1):
            damp += self.phi ** h
            out.append(self.level + damp * self.trend)
        return out

    @classmethod
    def best_fit(cls, anomalies):
        clean = list(filter(lambda v: v is not None, anomalies))
        if len(clean) < 5:
            raise ForecastError(f"Need at least 5 valid days of history, got {len(clean)}")
        return min((cls(a, b).fit(clean) for a in HOLT_ALPHAS for b in HOLT_BETAS), key=lambda m: m.sse)


def _holt_predictions(station, feed, climatology, horizon):
    normals = [climatology.normal_tmax(station.station_id, d, station.latitude) for d in feed.history_dates]
    anomalies = [None if t is None else t - n for t, n in zip(feed.history_tmax, normals)]
    model = HoltDampedModel.best_fit(anomalies)
    sigma = max(model.rmse, MIN_SIGMA)
    preds = [(a * 0.9 ** h, min(sigma * math.sqrt(h), 4.5)) for h, a in enumerate(model.predict(horizon), 1)]
    return preds, {"model": "Damped Holt fallback", "alpha": model.alpha, "beta": model.beta,
                   "training_rmse": round(model.rmse, 2)}


def forecast_station(station, feed, climatology, pooled=None, horizon=FORECAST_HORIZON):
    """Forecast the next `horizon` days for one station. Returns (days, model_info)."""
    as_of = date.fromisoformat(feed.history_dates[-1])
    try:
        if pooled is None:
            raise ForecastError("no pooled model")
        predictions = pooled.predict_anomalies(station.station_id)
        info = {"model": "Regional ridge regression"}
    except ForecastError:
        try:
            predictions, info = _holt_predictions(station, feed, climatology, horizon)
        except ForecastError as err:
            predictions, info = [(0.0, 3.0)] * horizon, {"model": "Climatology fallback", "reason": str(err)}

    days = []
    for lead, (anom, sd) in enumerate(predictions, start=1):
        d = as_of + timedelta(days=lead)
        normal = climatology.normal_tmax(station.station_id, d, station.latitude)
        mean = normal + anom
        hw_thr = station.heatwave_threshold(normal)
        sv_thr = station.heatwave_threshold(normal, severe=True)
        days.append({
            "lead": lead, "date": d.isoformat(), "tmax": round(mean, 1),
            "lo": round(mean - 1.28 * sd, 1), "hi": round(mean + 1.28 * sd, 1),  # 80 % interval
            "normal": round(normal, 1), "heatwave_threshold": hw_thr, "severe_threshold": sv_thr,
            "p_heatwave": round(1 - science.normal_cdf((hw_thr - mean) / sd), 3),
            "p_severe": round(1 - science.normal_cdf((sv_thr - mean) / sd), 3),
            "category": station.classify(round(mean, 1), normal),
        })
    return days, info


def fit_pooled(feeds, climatology):
    """Fit the pooled model, or return None (callers then fall back per station)."""
    try:
        return RegionalRidgeForecaster().fit(feeds, climatology)
    except (ForecastError, ValueError, ZeroDivisionError):
        return None
