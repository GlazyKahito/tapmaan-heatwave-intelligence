"""Phase II/V - Heatwave severity classification and the early warning engine.

The engine is explainable: it evaluates named rules, each contributing a sub-score
(0-100), and combines them with fixed weights from config.RISK_WEIGHTS. The final
score maps to IMD's impact-based colour codes (GREEN / YELLOW / ORANGE / RED).
Hard rules can raise the level regardless of the score (e.g. an observed severe heatwave).
"""

from collections import namedtuple

from . import science
from .config import ALERT_LEVELS, ALERT_META, LEVEL_CUTOFFS, RISK_WEIGHTS

RuleResult = namedtuple("RuleResult", "key title score weight fired detail")


class EarlyWarningEngine:
    def __init__(self, weights=RISK_WEIGHTS):
        self.weights = weights

    # ---- individual rules ---------------------------------------------------------
    @staticmethod
    def _imd_rule(category, departure):
        score = {science.NORMAL: 0, science.HEATWAVE: 70, science.SEVERE: 100}[category]
        if category == science.NORMAL and departure is not None and departure > 2.5:
            score = 25  # warmer than normal, approaching criteria
        return score, f"IMD category today: {category} (departure {departure:+.1f} C)"

    @staticmethod
    def _forecast_rule(forecast):
        near = forecast[:3]
        p = max((d["p_heatwave"] for d in near), default=0.0)
        ps = max((d["p_severe"] for d in near), default=0.0)
        score = min(100, p * 85 + ps * 40)
        return score, f"Max heatwave probability next 3 days {p:.0%} (severe {ps:.0%})"

    @staticmethod
    def _heat_index_rule(hi):
        score = min(100, max(0, (hi - 32) / (54 - 32) * 100))
        return score, f"Heat index {hi:.1f} C - {science.heat_index_band(hi)}"

    @staticmethod
    def _wet_bulb_rule(tw):
        score = min(100, max(0, (tw - 24) / (31 - 24) * 100))
        return score, f"Wet-bulb temperature {tw:.1f} C (31 C is dangerous even for healthy adults)"

    @staticmethod
    def _persistence_rule(streak):
        score = min(100, streak * 30)
        return score, f"{streak} consecutive heatwave day(s) up to today"

    # ---- combination --------------------------------------------------------------
    def assess(self, category, departure, forecast, heat_index, wet_bulb, streak):
        raw = {
            "imd_severity": ("IMD severity (observed)",) + self._imd_rule(category, departure),
            "forecast_probability": ("AI forecast (next 72 h)",) + self._forecast_rule(forecast),
            "heat_index": ("Heat index",) + self._heat_index_rule(heat_index),
            "wet_bulb": ("Humid heat (wet-bulb)",) + self._wet_bulb_rule(wet_bulb),
            "persistence": ("Persistence",) + self._persistence_rule(streak),
        }
        rules = [RuleResult(k, title, round(score, 1), self.weights[k], score >= 40, detail)
                 for k, (title, score, detail) in raw.items()]
        total = round(sum(r.score * r.weight for r in rules), 1)
        level = next((lvl for cut, lvl in LEVEL_CUTOFFS if total >= cut), "GREEN")

        overrides = []
        if category == science.SEVERE:
            overrides.append("Observed SEVERE HEATWAVE forces RED")
            level = "RED"
        elif category == science.HEATWAVE and ALERT_LEVELS.index(level) < ALERT_LEVELS.index("ORANGE"):
            overrides.append("Observed HEATWAVE forces at least ORANGE")
            level = "ORANGE"
        if wet_bulb >= 31 and ALERT_LEVELS.index(level) < ALERT_LEVELS.index("ORANGE"):
            overrides.append("Wet-bulb >= 31 C forces at least ORANGE")
            level = "ORANGE"
        return {
            "score": total, "level": level, "meta": ALERT_META[level],
            "rules": [r._asdict() for r in rules], "overrides": overrides,
            "explanation": self.explain(level, total, rules, overrides),
        }

    @staticmethod
    def explain(level, total, rules, overrides):
        top = sorted(rules, key=lambda r: r.score * r.weight, reverse=True)[:2]
        drivers = " and ".join(f"{r.title}: {r.detail}" for r in top)
        text = f"{level} ({ALERT_META[level]['label']}): risk score {total}/100. Main drivers - {drivers}."
        if overrides:
            text += " " + "; ".join(overrides) + "."
        return text


def heatwave_streak(station, dates, tmax_values, climatology):
    """Count consecutive heatwave days ending at the last date (persistence)."""
    streak = 0
    for d, t in zip(reversed(dates), reversed(tmax_values)):
        if t is None:
            break
        normal = climatology.normal_tmax(station.station_id, d, station.latitude)
        if station.classify(t, normal) == science.NORMAL:
            break
        streak += 1
    return streak
