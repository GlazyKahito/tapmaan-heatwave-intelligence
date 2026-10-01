"""Page renderers. Each function takes parsed query parameters and returns HTML."""

import json
from datetime import date

from ..config import ALERT_LEVELS, ALERT_META, IMD_CRITERIA, RISK_WEIGHTS
from ..database import PRESET_QUERIES, ClimateDatabase
from ..engine import HeatwaveIntelligence
from ..exceptions import InvalidStationError, QueryNotAllowedError
from ..stations_data import REGIONS
from .html import (LEVEL_COLOURS, badge, card, cat_class, e, fmt, kpi, logo_svg, notice, page, pct, seg, signed,
                   stat, table, url)
from .mapsvg import FIELDS, legend, render_map

MODE_LABELS = {"replay": "Replay · May 2024", "live": "Live · today", "simulated": "Simulated"}
TERRAIN_TEXT = {"plains": "Plains station", "coastal": "Coastal station", "hilly": "Hill station"}
_chart_cache = {}


def engine():
    return HeatwaveIntelligence.shared()


def cached_chart(key, fn, *args):
    if key not in _chart_cache:
        if len(_chart_cache) > 120:
            _chart_cache.clear()
        _chart_cache[key] = fn(*args)
    return _chart_cache[key]


class Params:
    """Query-string parameters shared by every page."""

    def __init__(self, query):
        get = lambda k, d=None: (query.get(k) or [d])[0]  # noqa: E731
        self.mode = get("mode", "replay") if get("mode") in MODE_LABELS else "replay"
        self.date = get("date")
        try:
            self.lead = max(0, min(int(get("lead", 0)), 5))
        except ValueError:
            self.lead = 0
        self.field = get("field", "tmax") if get("field") in FIELDS else "tmax"
        self.region = get("region", "ALL") if get("region") in REGIONS else "ALL"
        self.level = get("level", "ALL") if get("level") in ALERT_LEVELS else "ALL"
        self.query = query

    def base(self, as_of=None):
        out = {"mode": None if self.mode == "replay" else self.mode}
        if self.mode != "live" and (as_of or self.date):
            out["date"] = as_of or self.date
        return out


def mode_label(snap):
    if snap["mode"] == "live":
        return f"Live · {snap['as_of']}"
    return f"{MODE_LABELS[snap['mode']]} · {snap['as_of']}"


def nice_date(iso, fmt_="%d %b %Y"):
    return date.fromisoformat(iso).strftime(fmt_)


# ---------------------------------------------------------------- shared controls
def data_controls(p, snap, path, extra=None):
    extra = extra or {}
    mode_seg = seg([(m, lbl) for m, lbl in MODE_LABELS.items()], snap["mode"],
                   lambda m: url(path, mode=None if m == "replay" else m, **extra))
    date_ctrl = ""
    if snap["mode"] == "replay":
        eng = engine()
        lo, hi = eng.replay.date_range
        dates = eng.replay.dates[eng.replay.dates.index(lo):eng.replay.dates.index(hi) + 1]
        idx = dates.index(snap["as_of"])
        date_ctrl = (f'<form class="date-ctrl" method="get" action="{e(path)}" data-live-form>'
                     f'{"".join(f"<input type=hidden name={e(k)} value={e(v)}>" for k, v in extra.items() if v)}'
                     + ('<button type="button" class="btn ghost" data-play title="Play the heatwave">▶ Play</button>' if path == "/" else "")
                     + f'<input type="range" min="0" max="{len(dates) - 1}" value="{idx}" data-dates=\'{json.dumps(dates)}\' '
                     f'aria-label="Date">'
                     f'<input type="hidden" name="date" value="{e(snap["as_of"])}">'
                     f'<span class="date-label">{nice_date(snap["as_of"], "%a %d %b %Y")}</span></form>')
    elif snap["mode"] == "simulated":
        date_ctrl = (f'<form class="date-ctrl" method="get" action="{e(path)}" data-live-form>'
                     f'<input type="hidden" name="mode" value="simulated">'
                     f'{"".join(f"<input type=hidden name={e(k)} value={e(v)}>" for k, v in extra.items() if v)}'
                     f'<span class="label">Date</span><input class="input" type="date" name="date" value="{e(snap["as_of"])}" data-autosubmit>'
                     f'<span class="faint small">Synthetic weather built from 30-year normals</span></form>')
    else:
        date_ctrl = (f'<div class="date-ctrl"><span class="date-label">{nice_date(snap["as_of"], "%a %d %b %Y")}</span>'
                     f'<span class="faint small">Open-Meteo data · refreshed every 10 min · generated {e(snap["generated_at"])}</span></div>')
    return f'<div class="toolbar"><span class="label">Data</span>{mode_seg}{date_ctrl}</div>'


def notes_html(snap):
    return "".join(notice(e(n), "warn") for n in snap.get("notes", []))


# ---------------------------------------------------------------- Heatwave Watch (home)
def watch_page(p, partial=False):
    eng = engine()
    snap = eng.snapshot(p.mode, p.date)
    base = p.base(snap["as_of"])
    keep = {"lead": p.lead or None, "field": None if p.field == "tmax" else p.field,
            "region": None if p.region == "ALL" else p.region}
    href = lambda **kw: url("/", **{**base, **keep, **kw})  # noqa: E731

    lead_seg = seg([(0, "Observed")] + [(i, f"Day {i}") for i in range(1, 6)], p.lead,
                   lambda v: href(lead=v or None))
    field_seg = seg([("tmax", "Max temp"), ("anom", "Departure"), ("watch", "Heatwave watch")], p.field,
                    lambda v: href(field=None if v == "tmax" else v))
    region_opts = "".join(f'<option value="{k}" {"selected" if k == p.region else ""}>{e(v)}</option>'
                          for k, v in [("ALL", "National")] + list(REGIONS.items()))
    region_form = (f'<form method="get" action="/" data-live-form class="row">'
                   + "".join(f'<input type="hidden" name="{k}" value="{e(v)}">'
                             for k, v in {**base, "lead": p.lead or None,
                                          "field": None if p.field == "tmax" else p.field}.items() if v)
                   + f'<select name="region" data-autosubmit aria-label="Region">{region_opts}</select></form>')

    valid_for = snap["as_of"] if p.lead == 0 else snap["stations"][0]["forecast"][p.lead - 1]["date"]
    title = FIELDS[p.field][0] if p.field != "watch" else "Heatwave Watch (impact class)"
    map_svg = render_map(snap, eng.grid.cells, eng.grid.cell_regions(), p.field, p.lead, p.region, base)
    s = snap["summary"]
    lv = s["levels"]

    hottest = "".join(
        f'<a class="list-item" href="{e(url("/station/" + h["id"], **base))}"><span class="rank">{i}</span>'
        f'<span class="grow">{e(h["city"])}</span><span class="val">{h["tmax"]:.1f}°</span></a>'
        for i, h in enumerate(s["hottest"][:7], 1))
    anomalous = "".join(
        f'<a class="list-item" href="{e(url("/station/" + h["id"], **base))}"><span class="rank">{i}</span>'
        f'<span class="grow">{e(h["city"])}</span><span class="val">{signed(h["anomaly"])}°</span></a>'
        for i, h in enumerate(s["most_anomalous"][:5], 1))

    regions = "".join(
        f'<a class="region" style="--lvl:{LEVEL_COLOURS[r["worst_level"]]}" href="{e(href(region=r["code"]))}" data-nav>'
        f'<h4><span>{e(r["name"])}</span>{badge(r["worst_level"])}</h4>'
        f'<div class="big num">{fmt(r["mean_tmax"])}°C <small class="muted small">{signed(r["mean_anomaly"])}°</small></div>'
        f'<div class="sub">{r["heatwave_stations"]}/{r["stations"]} stations in heatwave · hottest {e(r["hottest"])} '
        f'{fmt(r["max_tmax"])}° · 72 h heatwave chance {pct(r["p_heatwave_72h"])}</div></a>'
        for r in snap["regions"])

    model = snap.get("model", {})
    w1 = model.get("weights", {}).get(1)
    model_txt = (f"Tomorrow's anomaly = {w1[0]:.2f} × today's anomaly {w1[1]:+.2f} × change since yesterday "
                 f"{w1[2]:+.2f} × regional anomaly {w1[3]:+.2f}" if w1 else e(model.get("model", "")))

    live = f"""
{data_controls(p, snap, "/", keep)}
{notes_html(snap)}
<div class="watch-layout">
  <section class="card map-card">
    <div class="map-head">
      <div>
        <h2>{e(title)}</h2>
        <div class="meta">Analysis date: <b>{nice_date(snap["as_of"])}</b> · Valid for: <b>{nice_date(valid_for)}</b>
        {" · observed" if p.lead == 0 else f" · forecast lead {p.lead}"}</div>
      </div>
      <div class="row">{region_form}</div>
    </div>
    <div class="map-tools row">{lead_seg}{field_seg}</div>
    <div class="map-wrap">{map_svg}</div>
    {legend(p.field)}
    <div class="map-note">0.5° grid interpolated (inverse-distance weighting) from 50 stations, twice as fine as IMD's
    gridded Tmax data. Click a station for its forecast and advisories. Not a political map.</div>
  </section>
  <aside class="stack">
    {card(f'<div class="kpis">{kpi(lv["RED"], "Red · act", "red")}{kpi(lv["ORANGE"], "Orange · prepare", "orange")}'
          f'{kpi(lv["YELLOW"], "Yellow · watch", "yellow")}{kpi(lv["GREEN"], "Green · normal", "green")}</div>',
          "Alert levels", "50 stations")}
    {card(f'<div class="stats">{stat("Mean Tmax", fmt(s["mean_tmax"], 1, "°"))}{stat("Highest Tmax", fmt(s["max_tmax"], 1, "°"))}'
          f'{stat("Peak heat index", fmt(s["max_heat_index"], 1, "°"))}{stat("Gi* hotspots", s["hotspots"])}</div>',
          "National picture")}
    {card(f'<div class="list">{hottest}</div>', "Hottest stations", "observed Tmax")}
    {card(f'<div class="list">{anomalous}</div>', "Furthest above normal", "departure")}
  </aside>
</div>
<div class="section-head"><h2>Region-wise status</h2><span class="muted small">Seven IMD temperature-homogeneous regions. Select one to zoom the map.</span></div>
<div class="regions">{regions}</div>
{card(f'<p class="small muted">{model_txt}. Retrained this morning on {model.get("training_samples", {}).get(1, "–")} '
      f'station-days from all 50 stations; separate weights for each lead day. '
      f'<a href="/skill">See how well it performed in 2024 →</a></p>', "Today's forecasting model", "explainable", "mt")}
"""
    if partial:
        return live
    hero = f"""
<div class="hero-strip">
  <div>
    <div class="eyebrow">Heatwave monitoring · prediction · early warning</div>
    <h1>India Heatwave Watch</h1>
    <p>Live and replayed maximum temperatures from 50 stations, AI forecasts up to five days ahead, IMD severity
    classes, statistically tested hotspots and stakeholder advisories. Press <b>Play</b> to watch the real
    May&nbsp;2024 heatwave build across North India.</p>
  </div>
  <div class="hero-logo">{logo_svg(0.62)}</div>
</div>"""
    return page("Heatwave Watch", hero + f'<div id="live" data-partial="/">{live}</div>', "/", mode_label(snap), snap["mode"])


# ---------------------------------------------------------------- Station
def station_page(p, station_id):
    eng = engine()
    try:
        d = eng.station_detail(station_id, p.mode, p.date)
    except InvalidStationError:
        return None
    from . import charts

    st, obs, alert = d["station"], d["obs"], d["alert"]
    base = p.base(d["as_of"])
    lvl = alert["level"]
    chart = cached_chart(("fc", d["mode"], d["as_of"], st["id"]), charts.forecast_chart, d)
    month = date.fromisoformat(d["as_of"]).month - 1
    cycle = cached_chart(("cycle", st["id"], month), charts.seasonal_cycle_chart,
                         eng.clim.monthly_means(st["id"]), month)

    rules = "".join(
        f'<div class="rule"><div class="t">{e(r["title"])}<small>{e(r["detail"])}</small></div>'
        f'<div class="bar"><i style="width:{r["score"]:.0f}%"></i></div>'
        f'<div class="num small r">{r["score"]:.0f} × {r["weight"]:.2f}</div></div>' for r in alert["rules"])
    overrides = "".join(f'<li>{e(o)}</li>' for o in alert["overrides"])

    fut = d["future"]
    rows = []
    for i, f in enumerate(d["forecast"]):
        check = fut["tmax"][i] if i < len(fut["tmax"]) else None
        rows.append([
            f'Day {f["lead"]}', nice_date(f["date"], "%a %d %b"), f'<b class="num">{f["tmax"]:.1f}</b>',
            f'<span class="num faint">{f["lo"]:.1f}–{f["hi"]:.1f}</span>', fmt(f["normal"]),
            fmt(f["heatwave_threshold"]), pct(f["p_heatwave"]), pct(f["p_severe"]),
            f'<span class="{cat_class(f["category"])}">{e(f["category"])}</span>',
            fmt(check) + (f' <span class="faint small">({signed(f["tmax"] - check)})</span>' if check is not None else ""),
        ])
    check_label = "Actual" if fut["kind"] == "observed" else "Reference"
    fc_table = table([("Lead", ""), ("Date", ""), ("Tmax °C", "r"), ("80% range", ""), ("Normal", "r"),
                      ("HW threshold", "r"), ("P(heatwave)", "r"), ("P(severe)", "r"), ("Category", ""),
                      (check_label, "r")], rows)

    advisories = "".join(
        f'<article class="advisory" data-adv="{e(a["id"])}" data-default="{e(a["status"])}">'
        f'<div class="row"><span class="chip hl">{e(a["audience"])}</span><span class="spacer"></span>'
        f'<span class="status {e(a["status"])}" data-status>{e(a["status"])}</span></div>'
        f'<h4>{e(a["headline"])}</h4><p class="small muted">{e(a["summary"])}</p>'
        f'<ul>{"".join(f"<li>{e(x)}</li>" for x in a["actions"])}</ul>'
        f'<div class="foot"><span class="tiny {"ok-t" if a["fact_check"]["passed"] else "bad-t"}">'
        f'{"✓" if a["fact_check"]["passed"] else "✗"} Fact check: {a["fact_check"]["numbers_checked"]} figures verified '
        f'against forecast data</span><span class="spacer"></span>'
        + (f'<button class="btn ok" data-approve>Approve</button><button class="btn bad" data-reject>Reject</button>'
           if a["requires_approval"] else '<span class="tiny faint">Low risk: released automatically</span>')
        + '</div></article>' for a in d["advisories"])

    messages = "".join(_message_card(m) for m in d["messages"])

    risk = "".join(f"<li>{e(x)}</li>" for x in st["risk_factors"])
    hw_days = eng.clim.heatwave_days(st["id"])
    recent = sum(v for y, v in hw_days.items() if int(y) >= 2015)
    older = sum(v for y, v in hw_days.items() if 2005 <= int(y) < 2015)

    body = f"""
{data_controls(p, d | {"generated_at": "", "notes": []}, "/station/" + st["id"])}
<div class="station-hero">
  <div>
    <div class="eyebrow"><a href="{e(url("/", **base))}">← Heatwave Watch</a> · {e(st["id"])} · {e(st["region_name"])}</div>
    <h1>{e(st["city"])} <small>{e(st["state"])} · {st["lat"]:.2f}°N {st["lon"]:.2f}°E</small></h1>
    <div class="lineage"><span class="chip">{e(TERRAIN_TEXT[st["terrain"]])}</span>
      <span class="chip">IMD threshold ≥ {IMD_CRITERIA[st["terrain"]]["min_tmax"]:.0f} °C</span>
      <span class="chip">{e(d["hotspot"])} (z = {fmt(d["hotspot_z"], 2)})</span></div>
  </div>
  <div class="hero-level">{badge(lvl)}<div class="faint small">{e(ALERT_META[lvl]["meaning"])}</div></div>
</div>
<div class="stats">
  {stat("Max temperature", fmt(obs["tmax"], 1, " °C"), f"normal {fmt(d['normal'])} °C")}
  {stat("Departure", signed(d["anomaly"]) + " °C", f'<span class="{cat_class(d["category"])}">{e(d["category"])}</span>')}
  {stat("Heat index", fmt(d["heat_index"], 1, " °C"), e(d["hi_band"]))}
  {stat("Wet-bulb", fmt(d["wet_bulb"], 1, " °C"), "humid-heat stress")}
  {stat("Humidity (min)", fmt(obs["humidity"], 0, " %"), f'wind {fmt(obs["wind"], 0)} km/h')}
  {stat("Min temperature", fmt(obs["tmin"], 1, " °C"), e(obs["condition"]))}
  {stat("Heatwave streak", d["streak"], "consecutive days")}
  {stat("Risk score", fmt(alert["score"], 0) + "/100", "early warning engine")}
</div>
<div class="grid cols-main mt">
  {card(f'<div class="chart-box">{chart}</div>', "14-day history and 5-day AI forecast", e(d["source"]))}
  {card(f'<div class="why">{rules}</div><div class="explain mt">{e(alert["explanation"])}</div>'
        + (f'<ul class="small muted">{overrides}</ul>' if overrides else ""), "Why this alert?", "explainable score")}
</div>
{card(fc_table, "Five-day outlook", "probabilities from the forecast error distribution", "mt")}
<div class="section-head"><h2>Stakeholder advisories</h2>
<span class="muted small">Drafted automatically from the forecast. ORANGE and RED advisories wait for a meteorologist's approval
(human-in-the-loop) before release. Decisions are saved in this browser.</span></div>
<div class="grid cols-2">{advisories}</div>
<div class="section-head"><h2>Dissemination channels</h2><span class="muted small">The same alert, formatted for each channel and language.</span></div>
<div class="grid cols-2">{messages}</div>
<div class="grid cols-2 mt">
  {card(f'<div class="chart-box">{cycle}</div><p class="tiny faint">Bars: mean monthly Tmax 1995–2024; whiskers: coolest to hottest year. '
        f'This month is highlighted.</p>', "Seasonal cycle", "30-year climatology")}
  {card(f'<ul class="small">{risk}</ul><div class="stats mt">{stat("Heatwave days 2005–14", older)}{stat("Heatwave days 2015–24", recent)}</div>',
        "Local risk profile")}
</div>
"""
    return page(f"{st['city']} heat outlook", body, "/", mode_label(d), d["mode"],
                f"Heatwave forecast, alert level and advisories for {st['city']}, {st['state']}.")


def _message_card(m):
    if m["channel"] == "Bulletin":
        meta, text = f'{m["chars"]} chars · email, radio and notice boards', f'<pre>{e(m["text"])}</pre>'
    else:
        parts = "part" if m["segments"] == 1 else "parts"
        meta, text = f'{m["encoding"]} · {m["chars"]} chars · {m["segments"]} SMS {parts}', f'<div class="txt">{e(m["text"])}</div>'
    return (f'<div class="message"><div class="hdr"><span class="chip">{e(m["channel"])}</span>'
            f'<span class="chip">{e(m["language"])}</span><span class="tiny faint">{meta}</span></div>{text}</div>')


# ---------------------------------------------------------------- Early warnings
def warnings_page(p):
    eng = engine()
    snap = eng.snapshot(p.mode, p.date)
    base = p.base(snap["as_of"])
    rows = sorted(snap["stations"], key=lambda r: r["alert"]["score"], reverse=True)
    if p.level != "ALL":
        rows = [r for r in rows if r["alert"]["level"] == p.level]
    if p.region != "ALL":
        rows = [r for r in rows if r["station"]["region"] == p.region]
    keep = {"region": None if p.region == "ALL" else p.region}
    level_seg = seg([("ALL", "All")] + [(lv, lv.title()) for lv in reversed(ALERT_LEVELS)], p.level,
                    lambda v: url("/warnings", **base, **keep, level=None if v == "ALL" else v))
    region_opts = "".join(f'<option value="{k}" {"selected" if k == p.region else ""}>{e(v)}</option>'
                          for k, v in [("ALL", "All regions")] + list(REGIONS.items()))
    region_form = (f'<form method="get" action="/warnings" class="row">'
                   + "".join(f'<input type="hidden" name="{k}" value="{e(v)}">'
                             for k, v in {**base, "level": None if p.level == "ALL" else p.level}.items() if v)
                   + f'<select name="region" data-autosubmit>{region_opts}</select></form>')

    trs, links = [], []
    for r in rows:
        st = r["station"]
        peak = max(r["forecast"][:3], key=lambda f: f["tmax"])
        trs.append([
            f'<b>{e(st["city"])}</b> <span class="faint small">{e(st["id"])}</span>', e(st["state"]), e(st["region"]),
            badge(r["alert"]["level"]), f'<span class="num">{r["alert"]["score"]:.0f}</span>',
            f'<span class="{cat_class(r["category"])}">{e(r["category"].title())}</span>',
            fmt(r["obs"]["tmax"]), signed(r["anomaly"]), fmt(r["heat_index"]),
            f'{fmt(peak["tmax"])} <span class="faint small">{nice_date(peak["date"], "%d %b")}</span>',
            pct(max(f["p_heatwave"] for f in r["forecast"][:3])), e(r["hotspot"].split(" (")[0]),
            f'<span class="status" data-queue="{e(st["id"])}-{e(r["obs"]["date"])}">'
            + ("DRAFT" if r["alert"]["level"] in ("ORANGE", "RED") else "AUTO") + "</span>",
        ])
        links.append(url("/station/" + st["id"], **base))
    tbl = table([("Station", ""), ("State", ""), ("Region", ""), ("Level", ""), ("Score", "r"), ("Category", ""),
                 ("Tmax", "r"), ("Dep.", "r"), ("Heat idx", "r"), ("Peak (72 h)", ""), ("P(HW 72 h)", "r"),
                 ("Hotspot", ""), ("Advisories", "")], trs, "", links)

    lv = snap["summary"]["levels"]
    red = [r for r in snap["stations"] if r["alert"]["level"] == "RED"]
    orange = [r for r in snap["stations"] if r["alert"]["level"] == "ORANGE"]
    bulletin = [
        f"NATIONAL HEAT BULLETIN · {nice_date(snap['as_of'], '%d %B %Y').upper()}",
        "=" * 60,
        f"RED (take action)   : {', '.join(r['station']['city'] for r in red) or 'none'}",
        f"ORANGE (be prepared): {', '.join(r['station']['city'] for r in orange) or 'none'}",
        f"Highest Tmax        : {snap['summary']['hottest'][0]['city']} {snap['summary']['hottest'][0]['tmax']:.1f} °C",
        f"Stations in heatwave: {sum(1 for r in snap['stations'] if r['category'] != 'NORMAL')} of 50",
        f"Statistical hotspots: {snap['summary']['hotspots']} station(s) with Gi* z ≥ 1.96",
    ]
    worst_regions = [r for r in snap["regions"] if r["worst_level"] in ("RED", "ORANGE")]
    if worst_regions:
        bulletin.append("Regions of concern  : " + ", ".join(f"{r['name']} ({r['worst_level']})" for r in worst_regions))
    body = f"""
<div class="page-head"><div><div class="eyebrow">Phase V · decision support</div><h1>Early Warning Centre</h1>
<p>Every station ranked by the early-warning engine. Each risk score combines observed IMD severity, the AI forecast,
heat index, humid heat and persistence. Open a station to review and approve its advisories.</p></div></div>
{data_controls(p, snap, "/warnings", {"level": None if p.level == "ALL" else p.level, **keep})}
<div class="grid cols-4">{kpi(lv["RED"], "Red · take action", "red")}{kpi(lv["ORANGE"], "Orange · be prepared", "orange")}
{kpi(lv["YELLOW"], "Yellow · be updated", "yellow")}{kpi(lv["GREEN"], "Green · no action", "green")}</div>
<div class="toolbar mt"><span class="label">Filter</span>{level_seg}{region_form}<span class="spacer"></span>
<span class="faint small">{len(rows)} station(s)</span></div>
{tbl}
<div class="grid cols-2 mt">
{card(f'<pre class="output">{e(chr(10).join(bulletin))}</pre>', "National heat bulletin", "generated text")}
{card('<ul class="small"><li><b>Observed</b>: an IMD heatwave forces at least ORANGE; a severe heatwave forces RED.</li>'
      '<li><b>Forecast</b>: the chance of a heatwave in the next 72 hours raises the score before the heat arrives (early warning).</li>'
      '<li><b>Human-in-the-loop</b>: ORANGE and RED advisories stay as <span class="status DRAFT">DRAFT</span> until approved on the station page.</li>'
      '<li><b>Fact check</b>: every temperature quoted in an advisory is checked against the forecast before release.</li></ul>'
      + "".join(f'<div class="rule"><div class="t">{e(k.replace("_", " ").title())}</div><div class="bar"><i style="width:{v * 100 / 0.35:.0f}%"></i></div>'
                f'<div class="num small r">{v:.2f}</div></div>' for k, v in RISK_WEIGHTS.items()),
      "How alerts are decided", "weights")}
</div>"""
    return page("Early Warnings", body, "/warnings", mode_label(snap), snap["mode"])


# ---------------------------------------------------------------- Forecast skill
def skill_page(p):
    eng = engine()
    from . import charts
    val = eng.validation()
    mae = cached_chart("skill_mae", charts.skill_mae_chart, val)
    ev = cached_chart("skill_ev", charts.skill_events_chart, val)
    reg = cached_chart("skill_reg", charts.region_mae_chart, val, REGIONS)
    l1 = val["leads"][0]
    l5 = val["leads"][-1]
    rows = [[f'Day {r["lead"]}', fmt(r["model"]["mae"], 2), fmt(r["persistence"]["mae"], 2), fmt(r["climatology"]["mae"], 2),
             fmt(r["model"]["rmse"], 2), signed(r["model"]["bias"], 2),
             f'<b class="{"pos" if r["skill_vs_persistence"] > 0 else "neg"}">{r["skill_vs_persistence"] * 100:+.1f}%</b>',
             fmt(r["events"]["pod"], 2), fmt(r["events"]["far"], 2), fmt(r["events"]["csi"], 2), fmt(r["events"]["brier"], 3)]
            for r in val["leads"]]
    tbl = table([("Lead", ""), ("MAE model", "r"), ("MAE persist.", "r"), ("MAE clim.", "r"), ("RMSE", "r"),
                 ("Bias", "r"), ("Skill vs persist.", "r"), ("POD", "r"), ("FAR", "r"), ("CSI", "r"), ("Brier", "r")], rows)
    body = f"""
<div class="page-head"><div><div class="eyebrow">Phase IV · forecast validation</div><h1>Forecast Skill</h1>
<p>A forecast is only useful if it can be trusted. Here the model is replayed day by day through the real 2024 heatwave
({nice_date(val["period"][0])} – {nice_date(val["period"][1])}). On each day it is trained only on data available up to
that day, then its forecasts are compared with what actually happened.</p></div></div>
<div class="stats">
  {stat("Forecasts verified", f'{val["forecasts"]:,}', f'{val["stations"]} stations × 5 lead days')}
  {stat("Day-1 error (MAE)", fmt(l1["model"]["mae"], 2, " °C"), f'persistence {fmt(l1["persistence"]["mae"], 2)} °C')}
  {stat("Day-5 error (MAE)", fmt(l5["model"]["mae"], 2, " °C"), f'persistence {fmt(l5["persistence"]["mae"], 2)} °C')}
  {stat("Day-5 skill", f'{l5["skill_vs_persistence"] * 100:+.1f}%', "error reduction vs persistence")}
  {stat("Day-1 heatwave detection", pct(l1["events"]["pod"]), f'false alarms {pct(l1["events"]["far"])}')}
</div>
<div class="grid cols-2 mt">
  {card(f'<div class="chart-box">{mae}</div>', "Temperature error by lead time", "lower is better")}
  {card(f'<div class="chart-box">{ev}</div>', "Heatwave event detection", "POD ↑ · CSI ↑ · FAR ↓")}
</div>
{card(tbl, "Verification table", "2024 backtest", "mt")}
<div class="grid cols-2 mt">
  {card(f'<div class="chart-box">{reg}</div>', "Day-1 error by region")}
  {card('''<ul class="small">
  <li><b>Persistence</b> ("tomorrow = today") is a tough baseline during a heatwave because hot spells last for days.
  The model must beat it to be worth using, and it does at every lead time.</li>
  <li><b>Climatology</b> ("tomorrow = normal") fails badly in a heatwave. That is exactly why anomaly-aware forecasting matters.</li>
  <li><b>POD</b>: share of real heatwave days that were forecast (probability ≥ 50%). <b>FAR</b>: share of heatwave forecasts that did not happen.
  <b>CSI</b>: hits / (hits + misses + false alarms). <b>Brier</b>: mean squared error of the probabilities.</li>
  <li>Detection drops with lead time, which is honest and expected. Day 1–2 warnings are reliable; Day 4–5 are a heads-up.</li>
  <li>Data: ERA5 reanalysis. Station observations run 1–3 °C hotter, so absolute thresholds are reached less often in this data.</li></ul>''',
        "Reading the scores")}
</div>"""
    return page("Forecast Skill", body, "/skill", "Backtest · 2024", "replay")


# ---------------------------------------------------------------- Climate trends
def climate_page(p):
    eng = engine()
    from . import charts
    rep = eng.climate_analysis()
    heat = cached_chart("season", charts.season_heatmap, rep)
    trend = cached_chart("trend", charts.trend_chart, rep)
    hwd = cached_chart("hwdays", charts.heatwave_days_chart, rep)
    rows = [[f'<span class="swatch" style="background:{charts.REGION_COLOURS[s["region"]]}"></span>{e(s["name"])}',
             signed(s["mam_trend_per_decade"], 2) + " °C", signed(s["hw_days_trend_per_decade"], 2) + " days",
             f'{s["years"][s["heatwave_days"].index(max(s["heatwave_days"]))]} '
             f'<span class="faint small">({fmt(max(s["heatwave_days"]), 1)} d)</span>']
            for s in rep["series"]]
    tbl = table([("Region", ""), ("Tmax / decade", "r"), ("HW days / decade", "r"), ("Worst year", "r")], rows)
    tbl += ('<p class="tiny faint mt">Tmax trend uses the March–May mean; heatwave days are averaged over the '
            'stations in each region. Positive numbers mean more heat.</p>')
    body = f"""
<div class="page-head"><div><div class="eyebrow">Phase II · spatio-temporal analysis</div><h1>Climate Trends</h1>
<p>Thirty years ({e(rep["period"][0][:4])}–{e(rep["period"][1][:4])}) of daily maximum temperature for all 50 stations,
split into the seven IMD temperature-homogeneous regions and four seasons. Heatwave days are counted with the official IMD criteria.</p></div></div>
<div class="grid cols-main">
  {card(f'<div class="chart-box">{heat}</div>', "Region × season mean Tmax", "°C")}
  {card(tbl, "Warming and heatwave trends", "least-squares fit")}
</div>
{card(f'<div class="chart-box">{trend}</div>', "Pre-monsoon maximum temperature by region", "thin: yearly · bold: 5-year rolling mean", "mt")}
{card(f'<div class="chart-box">{hwd}</div>', "Heatwave days per station per year (national mean)", "red bars: top 20% years", "mt")}
<p class="tiny faint mt">Source: {e(rep["source"])}. Seasons: Winter (Jan–Feb), Pre-monsoon (Mar–May), Monsoon (Jun–Sep), Post-monsoon (Oct–Dec).</p>
"""
    return page("Climate Trends", body, "/climate", "Climatology · 1995–2024", "replay")


# ---------------------------------------------------------------- AWS network
def aws_page(p):
    eng = engine()
    from . import charts
    from ..aws_network import AWSNetwork

    q = p.query
    get = lambda k, d: (q.get(k) or [d])[0]  # noqa: E731
    try:
        n = max(3, min(int(get("n", 15)), 50))
        fault = max(0.0, min(float(get("fault", 0.15)), 0.6))
        seed = int(get("seed", 42))
    except ValueError:
        n, fault, seed = 15, 0.15, 42
    snap = eng.snapshot(p.mode, p.date)
    sids = [r["station"]["id"] for r in snap["stations"] if p.region == "ALL" or r["station"]["region"] == p.region][:n]
    _, provider, as_of = eng.resolve(p.mode, p.date)
    feeds = provider.fetch(eng.registry, as_of)
    report = AWSNetwork(fault_rate=fault, seed=seed).sweep({s: feeds[s].observation for s in sids})
    gantt = charts.aws_gantt(report)
    city = {s.station_id: s.city for s in eng.stations}
    c = report["counts"]
    log = "".join(
        f'<div class="e-{e(ev["status"])}">{ev["start_ms"]:>7.1f} ms  {ev["thread"]:<12} {city[ev["station_id"]]:<18} '
        f'{ev["status"].upper():<13} {e(ev["value"] if ev["status"] == "ok" else ev["message"])}</div>'
        for ev in report["events"])
    warn = "".join(f'<li><span class="badge {"RED" if w["level"] == "CRITICAL" else "ORANGE"}">{e(w["level"])}</span> '
                   f'<b>{e(city[w["station_id"]])}</b>: {e(w["text"])}</li>' for w in report["warnings"]) or "<li>No thresholds exceeded.</li>"
    region_opts = "".join(f'<option value="{k}" {"selected" if k == p.region else ""}>{e(v)}</option>'
                          for k, v in [("ALL", "All regions")] + list(REGIONS.items()))
    hidden = "".join(f'<input type="hidden" name="{k}" value="{e(v)}">' for k, v in p.base(snap["as_of"]).items() if v)
    body = f"""
<div class="page-head"><div><div class="eyebrow">Phase III · IoT automated weather stations</div><h1>AWS Network Monitor</h1>
<p>A simulated network of IoT automated weather stations. Three monitor threads (temperature, humidity and wind) poll the nodes
<b>at the same time</b> over a lossy radio link. Bad packets, missing values and timeouts are caught one reading at a time,
so a failing sensor never stops the sweep. Readings come from the {e(MODE_LABELS[snap["mode"]])} data for {e(nice_date(snap["as_of"]))}.</p></div></div>
<form class="toolbar" method="get" action="/aws">{hidden}
  <span class="label">Nodes</span><input class="input" type="number" name="n" min="3" max="50" value="{n}" style="width:76px">
  <span class="label">Fault rate</span><input class="input" type="number" name="fault" min="0" max="0.6" step="0.05" value="{fault}" style="width:86px">
  <span class="label">Region</span><select name="region">{region_opts}</select>
  <input type="hidden" name="seed" value="{seed + 1}">
  <button class="btn primary" type="submit">Run new sweep</button>
  <span class="faint small">seed {seed}</span>
</form>
<div class="stats">
  {stat("Wall-clock time", fmt(report["wall_ms"], 0, " ms"), "3 threads in parallel")}
  {stat("Sum of read times", fmt(report["sequential_ms"], 0, " ms"), "if done one by one")}
  {stat("Concurrency gain", fmt(report["speedup"], 2, "×"), "I/O overlap")}
  {stat("Good readings", c.get("ok", 0), f'of {len(report["events"])}')}
  {stat("Invalid values", c.get("invalid", 0), "range check failed")}
  {stat("Missing / timeouts", c.get("missing", 0) + c.get("comm_failure", 0), "handled, not fatal")}
</div>
{card(f'<div class="chart-box">{gantt}</div>', "Thread timeline", "each block is one sensor read", "mt")}
<div class="grid cols-2 mt">
  {card(f'<div class="log">{log}</div>', "Event log", "thread-safe, lock-protected")}
  {card(f'<ul class="warn-list">{warn}</ul>', "Threshold warnings from valid readings", "temp ≥ 40 °C · humid heat · wind ≥ 40 km/h")}
</div>"""
    return page("AWS Network", body, "/aws", mode_label(snap), snap["mode"])


# ---------------------------------------------------------------- Data explorer
def data_page(p):
    eng = engine()
    snap = eng.snapshot(p.mode, p.date)
    q = p.query
    sql = (q.get("q") or [None])[0]
    preset = (q.get("preset") or [None])[0]
    if sql is None:
        try:
            sql = PRESET_QUERIES[int(preset)][1] if preset is not None else PRESET_QUERIES[11][1]
        except (ValueError, IndexError):
            sql = PRESET_QUERIES[0][1]
    with ClimateDatabase() as db:
        db.load_stations(eng.stations)
        db.load_readings(snap["stations"])
        counts = db.table_counts()
        try:
            res, err = db.run_readonly(sql), None
        except QueryNotAllowedError as ex:
            res, err = None, str(ex)
    base = p.base(snap["as_of"])
    presets = "".join(f'<a class="preset {"on" if s == sql else ""}" href="{e(url("/data", **base, preset=i))}">{e(t)}</a>'
                      for i, (t, s) in enumerate(PRESET_QUERIES))
    if err:
        result = f'<div class="error-box">⚠ {e(err)}</div>'
    else:
        rows = [[e(v) if not isinstance(v, float) else f"{v:g}" for v in r] for r in res["rows"]]
        result = (f'<div class="ok-box">{len(res["rows"])} row(s){" (first 200 shown)" if res["truncated"] else ""}</div>'
                  + table([(c, "") for c in res["columns"]], rows))
    hidden = "".join(f'<input type="hidden" name="{k}" value="{e(v)}">' for k, v in base.items() if v)
    body = f"""
<div class="page-head"><div><div class="eyebrow">SQLite · read-only</div><h1>Data Explorer</h1>
<p>The current snapshot ({e(MODE_LABELS[snap["mode"]])}, {e(nice_date(snap["as_of"]))}) is loaded into an SQLite database with two tables:
<code>stations</code> ({counts["stations"]} rows) and <code>readings</code> ({counts["readings"]} rows). Pick a saved query or write your own SELECT.
Only reads are allowed: an SQLite authorizer blocks any statement that would change data.</p></div></div>
<div class="sql-layout">
  {card(f'<div class="presets">{presets}</div>', "Saved queries")}
  <div class="stack">
    <form method="get" action="/data" class="card">{hidden}
      <textarea class="code" name="q" spellcheck="false" aria-label="SQL query">{e(sql)}</textarea>
      <div class="row mt"><button class="btn primary" type="submit">Run query</button>
      <span class="faint small">stations(station_id, city, state, latitude, longitude, region, terrain) ·
      readings(reading_id, station_id, obs_date, tmax, tmin, humidity, wind_speed, heat_index, anomaly, category, alert_level)</span></div>
    </form>
    {result}
  </div>
</div>"""
    return page("Data Explorer", body, "/data", mode_label(snap), snap["mode"])


# ---------------------------------------------------------------- About
def about_page(p):
    eng = engine()
    layers = [
        ("1", "#7fb2ff", "Data acquisition", "Thirty years of ERA5 daily Tmax (1995–2024) for normals and trends, the real April–June 2024 "
         "heatwave for replay, and live Open-Meteo data fetched in parallel threads. If a source fails, a resilient provider "
         "falls back station by station to simulated data, so the dashboard never goes blank.", ["providers", "climatology", "grd_reader"]),
        ("2", "#38d39f", "Analytics", "Region-wise segmentation into the seven IMD homogeneous regions, four seasons, trend analysis "
         "and 0.5° gridding by inverse-distance weighting.", ["spatial", "analytics"]),
        ("3", "#ffb020", "AI heatwave intelligence", "A pooled ridge-regression forecaster, retrained every day on all stations, "
         "predicts Tmax anomalies 1–5 days ahead with calibrated uncertainty. IMD criteria classify severity. Getis-Ord Gi* "
         "finds statistically significant hotspots.", ["forecast", "alerts", "spatial"]),
        ("4", "#ff6a3d", "Forecast validation", "Walk-forward backtesting on the 2024 heatwave against persistence and climatology "
         "baselines: MAE, RMSE, bias, POD, FAR, CSI and Brier score.", ["validation"]),
        ("5", "#b38cff", "Decision support", "Explainable early-warning scores, impact-based colour codes, advisories for "
         "citizens, farmers, health departments and local authorities, a fact-check guardrail, human approval, and SMS in "
         "English, हिन्दी and मराठी.", ["engine", "advisories", "webui"]),
    ]
    layer_html = "".join(
        f'<div class="layer"><div class="no" style="background:{c}">{n}</div><div><h4>{e(t)}</h4><p class="small muted">{e(d)}</p>'
        f'<div class="mods">{"".join(f"<span class=chip>tapmaan/{m}.py</span>" for m in mods)}</div></div></div>'
        for n, c, t, d, mods in layers)
    gov = [("Responsible AI", "High", "Every alert shows its rule scores and a plain-English explanation; forecasts carry uncertainty ranges and probabilities."),
           ("AI security & trust", "High", "Sensor values are range-checked; corrupt or missing data is isolated; the model is validated against baselines."),
           ("Generative advisories", "High", "Advisory text comes from audited templates behind an AdvisoryGenerator interface, and a fact checker verifies every number."),
           ("Human-in-the-loop", "High", "ORANGE and RED advisories stay drafts until a meteorologist approves them."),
           ("Privacy", "Low", "Only weather data is processed; no personal data is collected."),
           ("Governance", "Medium", "Clearly labelled as a research prototype; official warnings remain with IMD.")]
    gov_tbl = table([("Area", ""), ("Relevance", ""), ("How Tapmaan handles it", "")],
                    [[f"<b>{e(a)}</b>", e(r), f'<span class="small">{e(t)}</span>'] for a, r, t in gov])
    body = f"""
<div class="hero-strip"><div><div class="eyebrow">About the project</div><h1>Tapmaan · तापमान</h1>
<p>A heatwave intelligence platform for India built around use case KJS-CES-01, <i>Climate Intelligence for
Heatwave Monitoring, Prediction, and Early Warning</i> (collaborating organisation: India Meteorological Department,
Mumbai-Pune). It turns raw temperature data into forecasts, severity levels, hotspots and advisories that people can act on.</p></div>
<div class="hero-logo">{logo_svg(0.62)}</div></div>
<div class="grid cols-main">
  {card(f'<div class="layers">{layer_html}</div>', "Five-layer architecture", "mirrors the use-case conceptual schema")}
  <div class="stack">
    {card('''<ul class="small"><li><b>Plains</b>: Tmax ≥ 40 °C and departure ≥ 4.5 °C → heatwave; &gt; 6.4 °C → severe.
    Or actual Tmax ≥ 45 °C → heatwave, ≥ 47 °C → severe.</li><li><b>Coastal</b>: Tmax ≥ 37 °C with departure ≥ 4.5 °C.</li>
    <li><b>Hilly</b>: Tmax ≥ 30 °C with departure ≥ 4.5 °C.</li><li>Normals: smoothed 1995–2024 day-of-year mean per station.</li></ul>''',
          "IMD heatwave criteria")}
    {card(f'''<ul class="small"><li><b>Core</b>: Python standard library: OOP model, threads, SQLite, statistics.</li>
    <li><b>Charts</b>: Matplotlib + Seaborn with Pandas and NumPy, rendered to SVG on the server.</li>
    <li><b>Web</b>: pages, map and charts generated by Python (<code>http.server</code> handler) on Vercel.</li>
    <li><b>Desktop</b>: Tkinter Heatwave Operations Console, run with <code>python desktop.py</code>.</li>
    <li><b>Stations</b>: {len(eng.stations)} across {len(REGIONS)} regions.</li></ul>''', "Technology")}
  </div>
</div>
{card(gov_tbl, "AI governance", "from the use-case framework", "mt")}
<div class="grid cols-2 mt">
  {card('''<ul class="small"><li>ERA5 reanalysis via the Open-Meteo archive API: normals, trends and the 2024 replay.</li>
  <li>Open-Meteo forecast API: live mode.</li><li>Ready for IMD 1° gridded Tmax (.grd) files through <code>IMDGridReader</code>.</li>
  <li>Station list and region mapping prepared for this project (approximate).</li></ul>''', "Data sources")}
  {card('''<ul class="small"><li>Reanalysis data is smoother than station data, so peaks are 1–3 °C lower than IMD observations.</li>
  <li>The forecaster uses temperature history only; it does not use the dynamics of a weather model.</li>
  <li>The AWS network is simulated; no real hardware is polled.</li>
  <li>Advisories are template-based; an LLM generator can be plugged in through the same interface.</li></ul>''', "Limitations")}
</div>"""
    return page("About", body, "/about", "Project", "replay")


def not_found_page():
    body = ('<div class="page-head"><div><div class="eyebrow">404</div><h1>Page not found</h1>'
            '<p>That page does not exist. <a href="/">Back to the Heatwave Watch →</a></p></div></div>')
    return page("Not found", body, "", "", "replay")
