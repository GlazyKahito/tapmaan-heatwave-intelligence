"""Phase V - Stakeholder advisories, dissemination channels and human-in-the-loop review.

* StakeholderAdvisor (ABC) -> Citizen / Farmer / Health / Authority advisors (polymorphism)
* AdvisoryGenerator (ABC)  -> TemplateAdvisoryGenerator. The use case asks for LLM-assisted
  generation; the generator sits behind an abstract interface so an LLM-backed subclass can
  replace the template one without touching the rest of the system.
* FactChecker              -> guardrail: every temperature quoted in an advisory must match
  the forecast data (factual consistency, Responsible AI).
* AlertChannel (ABC)       -> SMSChannel -> HindiSMSChannel / MarathiSMSChannel (multilevel),
  BulletinChannel. Messages respect SMS encodings (GSM-7 vs UCS-2 for Indic scripts).
Every ORANGE/RED advisory starts as DRAFT and must be approved by a meteorologist in the UI.
"""

import re
import textwrap
from abc import ABC, abstractmethod

from .config import ALERT_META, APP_NAME


# ---------------------------------------------------------------- stakeholder advisors
class StakeholderAdvisor(ABC):
    audience = "Stakeholder"
    icon = "users"

    @abstractmethod
    def actions(self, ctx):
        """Return a list of recommended actions for this audience."""

    def headline(self, ctx):
        lvl = ctx["level"]
        if lvl == "GREEN":
            return f"No heat warning for {ctx['city']}"
        return f"{ALERT_META[lvl]['label'].upper()}: heat risk in {ctx['city']}"

    def summary(self, ctx):
        return (f"Max temperature {ctx['tmax']:.1f} °C today (normal {ctx['normal']:.1f} °C). "
                f"Forecast peak {ctx['peak_tmax']:.1f} °C on {ctx['peak_date']}, "
                f"heatwave chance {ctx['p_heatwave']:.0%} in the next 72 hours.")

    def build(self, ctx):
        return {"audience": self.audience, "icon": self.icon, "headline": self.headline(ctx),
                "summary": self.summary(ctx), "actions": self.actions(ctx)}


class CitizenAdvisor(StakeholderAdvisor):
    audience, icon = "Citizens", "users"

    def actions(self, ctx):
        base = ["Drink water often, even if you are not thirsty.",
                "Wear light, loose cotton clothes and cover your head outdoors."]
        if ctx["level"] in ("ORANGE", "RED"):
            base += ["Avoid going out in the sun between 12 noon and 4 pm.",
                     "Check on elderly neighbours, children and people living alone.",
                     "Never leave children or pets in parked vehicles."]
        if ctx["level"] == "RED":
            base.append("Seek medical help at once for dizziness, confusion or no sweating (heat stroke).")
        return base


class FarmerAdvisor(StakeholderAdvisor):
    audience, icon = "Farmers", "sprout"

    def actions(self, ctx):
        acts = ["Irrigate in the early morning or evening to cut evaporation losses."]
        if ctx["level"] != "GREEN":
            acts += ["Apply mulch to keep soil moisture in standing crops.",
                     "Give livestock shade and clean drinking water; avoid grazing at noon."]
        if ctx["level"] in ("ORANGE", "RED"):
            acts += ["Postpone spraying and transplanting during peak heat hours.",
                     "Field workers should rest in shade every hour."]
        return acts


class HealthAdvisor(StakeholderAdvisor):
    audience, icon = "Health Departments", "hospital"

    def actions(self, ctx):
        acts = [f"Heat index is {ctx['heat_index']:.1f} °C ({ctx['hi_band']}); review heat-illness case reports daily."]
        if ctx["level"] != "GREEN":
            acts.append("Stock ORS, IV fluids and ice packs in primary health centres.")
        if ctx["level"] in ("ORANGE", "RED"):
            acts += ["Activate cool rooms / heat-stroke wards in district hospitals.",
                     "Alert ambulance services (108) for heat emergencies."]
        return acts


class AuthorityAdvisor(StakeholderAdvisor):
    audience, icon = "Local Authorities", "landmark"

    def actions(self, ctx):
        acts = ["Keep the heat action plan contact list up to date."]
        if ctx["level"] != "GREEN":
            acts.append("Open drinking-water points at bus stands, markets and labour hubs.")
        if ctx["level"] in ("ORANGE", "RED"):
            acts += ["Shift outdoor work and school hours away from 12-4 pm.",
                     "Keep public parks and shelters open as cooling centres."]
        if ctx["level"] == "RED":
            acts.append("Convene the district disaster management authority today.")
        return acts


# ---------------------------------------------------------------- generator + guardrail
class AdvisoryGenerator(ABC):
    @abstractmethod
    def generate(self, ctx):
        """Return a list of advisory dicts for the given station context."""


class TemplateAdvisoryGenerator(AdvisoryGenerator):
    def __init__(self, advisors=None):
        self.advisors = advisors or [CitizenAdvisor(), FarmerAdvisor(), HealthAdvisor(), AuthorityAdvisor()]
        self.checker = FactChecker()

    def generate(self, ctx):
        out = []
        for adv in self.advisors:
            item = adv.build(ctx)
            text = " ".join([item["headline"], item["summary"]] + item["actions"])
            item["id"] = f"{ctx['station_id']}-{ctx['date']}-{adv.audience.split()[0].lower()}"
            item["fact_check"] = self.checker.verify(text, ctx)
            item["requires_approval"] = ctx["level"] in ("ORANGE", "RED")
            item["status"] = "DRAFT" if item["requires_approval"] else "AUTO-APPROVED"
            out.append(item)
        return out


class FactChecker:
    """Every '<number> °C' in a text must be one of the values in the data context."""

    PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*°C")

    def verify(self, text, ctx):
        allowed = {round(float(ctx[k]), 1) for k in ("tmax", "normal", "peak_tmax", "heat_index", "wet_bulb")}
        quoted = [float(x) for x in self.PATTERN.findall(text)]
        problems = [q for q in quoted if round(q, 1) not in allowed]
        return {"passed": not problems, "numbers_checked": len(quoted), "problems": problems}


# ---------------------------------------------------------------- dissemination channels
class AlertChannel(ABC):
    name = "channel"
    language = "English"

    @abstractmethod
    def render(self, ctx):
        """Return the message text for this channel."""

    @staticmethod
    def sms_segments(text):
        """GSM-7 messages hold 160 chars (153 when split); Unicode (UCS-2) holds 70 (67)."""
        unicode = any(ord(ch) > 127 for ch in text)
        single, multi = (70, 67) if unicode else (160, 153)
        n = len(text)
        return {"encoding": "UCS-2" if unicode else "GSM-7", "chars": n,
                "segments": 1 if n <= single else -(-n // multi)}

    def package(self, ctx):
        text = self.render(ctx)
        return {"channel": self.name, "language": self.language, "text": text, **self.sms_segments(text)}


class SMSChannel(AlertChannel):
    name = "SMS"
    HEADLINES = {"GREEN": "Normal day", "YELLOW": "Heat watch", "ORANGE": "HEATWAVE ALERT",
                 "RED": "SEVERE HEATWAVE WARNING"}

    def headline(self, level):
        return self.HEADLINES[level]

    def render(self, ctx):
        msg = (f"{ctx['city'].upper()}: {self.headline(ctx['level'])}. Max {ctx['tmax']:.0f}C, "
               f"peak {ctx['peak_tmax']:.0f}C on {ctx['peak_day']}. Avoid sun 12-4pm, drink water. -{APP_NAME}")
        return msg if len(msg) <= 160 else msg[:157] + "..."


class HindiSMSChannel(SMSChannel):
    name, language = "SMS", "हिन्दी"
    HEADLINES = {"GREEN": "सामान्य स्थिति", "YELLOW": "गर्मी से सावधान", "ORANGE": "लू की चेतावनी",
                 "RED": "गंभीर लू चेतावनी"}

    def render(self, ctx):
        return (f"{ctx['city']}: {self.headline(ctx['level'])}। अधिकतम तापमान {ctx['tmax']:.0f}°C। "
                f"दोपहर 12-4 बजे धूप से बचें, पानी पीते रहें। -{APP_NAME}")


class MarathiSMSChannel(SMSChannel):
    name, language = "SMS", "मराठी"
    HEADLINES = {"GREEN": "सामान्य स्थिती", "YELLOW": "उष्णतेपासून सावध रहा", "ORANGE": "उष्णतेच्या लाटेचा इशारा",
                 "RED": "तीव्र उष्णतेच्या लाटेचा इशारा"}

    def render(self, ctx):
        return (f"{ctx['city']}: {self.headline(ctx['level'])}. कमाल तापमान {ctx['tmax']:.0f}°C. "
                f"दुपारी 12 ते 4 उन्हात जाणे टाळा, भरपूर पाणी प्या. -{APP_NAME}")


class BulletinChannel(AlertChannel):
    name = "Bulletin"
    WIDTH = 64

    def render(self, ctx):
        w = self.WIDTH
        rule = "=" * w
        lines = [rule, f"{APP_NAME.upper()} HEATWAVE BULLETIN".center(w), rule,
                 f"{'Station':<14}: {ctx['station_id']} - {ctx['city']}, {ctx['state']}",
                 f"{'Valid for':<14}: {ctx['date']}",
                 f"{'Alert level':<14}: {ctx['level']} ({ALERT_META[ctx['level']]['label']})",
                 f"{'Category':<14}: {ctx['category']}",
                 f"{'Max temp':<14}: {ctx['tmax']:.1f} C (normal {ctx['normal']:.1f} C, "
                 f"departure {ctx['departure']:+.1f} C)",
                 f"{'Heat index':<14}: {ctx['heat_index']:.1f} C - {ctx['hi_band']}",
                 "-" * w, "OUTLOOK".center(w, " ")]
        for d in ctx["forecast"]:
            lines.append(f"  Day {d['lead']}  {d['date']}  {d['tmax']:>5.1f} C   "
                         f"heatwave chance {d['p_heatwave']:>4.0%}")
        lines += ["-" * w]
        lines += textwrap.wrap(ctx["explanation"], width=w)
        lines += [rule]
        return "\n".join(lines)


DEFAULT_CHANNELS = (SMSChannel(), HindiSMSChannel(), MarathiSMSChannel(), BulletinChannel())


def disseminate(ctx, channels=DEFAULT_CHANNELS):
    """Same call, different output per channel - runtime polymorphism."""
    return [ch.package(ctx) for ch in channels]
