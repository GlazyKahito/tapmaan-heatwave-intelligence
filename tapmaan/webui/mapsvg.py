"""Gridded India heat map rendered as SVG by Python.

Each 1-degree cell is a <rect> coloured by the selected field (Tmax, anomaly or heatwave
watch probability). Stations are clickable markers coloured by alert level; Getis-Ord
hotspots get a dashed ring. Regional view zooms the viewBox onto one IMD region.
"""

import math

from .html import LEVEL_COLOURS, e, url

LON0, LON1, LAT0, LAT1 = 66.0, 99.0, 5.5, 38.5
K = 24.0                          # pixels per degree of latitude
STEP = 0.5                        # grid spacing in degrees (matches config.GRID_STEP_DEG)
KX = K * math.cos(math.radians(22))  # equirectangular correction at India's mid-latitude
LABELLED = {"WS103", "WS102", "WS104", "WS105", "WS106", "WS107", "WS108", "WS109", "WS110", "WS112",
            "WS101", "WS134", "WS132", "WS138", "WS125", "WS119", "WS123", "WS143"}

TEMP_STOPS = [(15, "#3b2c97"), (20, "#2f6fd0"), (25, "#36b6e0"), (29, "#6fdc8c"), (33, "#e6e94a"),
              (36, "#ffc23d"), (39, "#ff8c1a"), (42, "#e8352b"), (45, "#9c1020"), (48, "#4d0610")]
ANOM_STOPS = [(-6, "#2f6fd0"), (-3, "#6fb8e8"), (0, "#e9edf2"), (2.5, "#ffd166"), (4.5, "#ff8c1a"),
              (6.5, "#e8352b"), (9, "#7a0a16")]


def _rgb(h):
    n = int(h[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def ramp(stops):
    parsed = [(v, _rgb(c)) for v, c in stops]

    def colour(v):
        if v is None:
            return None
        if v <= parsed[0][0]:
            return "#%02x%02x%02x" % parsed[0][1]
        for (v0, c0), (v1, c1) in zip(parsed, parsed[1:]):
            if v <= v1:
                t = (v - v0) / (v1 - v0)
                return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
        return "#%02x%02x%02x" % parsed[-1][1]
    return colour


temp_colour = ramp(TEMP_STOPS)
anom_colour = ramp(ANOM_STOPS)


def impact_colour(p):
    if p is None:
        return None
    if p >= 0.6:
        return "#ff6a00"
    if p >= 0.3:
        return "#f4c430"
    return "#1b2846"


def gradient_css(stops):
    lo, hi = stops[0][0], stops[-1][0]
    return "linear-gradient(90deg," + ",".join(f"{c} {(v - lo) / (hi - lo) * 100:.0f}%" for v, c in stops) + ")"


def px(lat, lon):
    return (lon - LON0) * KX, (LAT1 - lat) * K


FIELDS = {
    "tmax": ("Maximum temperature", "°C"),
    "anom": ("Departure from normal", "°C"),
    "watch": ("Heatwave watch", ""),
}


def field_values(snapshot, field, lead):
    grid = snapshot["grid"]
    if field == "watch":
        return grid[f"p_{lead}"], impact_colour
    if field == "anom":
        return grid[f"anom_{lead}"], anom_colour
    return grid[f"tmax_{lead}"], temp_colour


def render_map(snapshot, cells, cell_regions, field="tmax", lead=0, region="ALL", link_params=None):
    values, colour = field_values(snapshot, field, lead)
    w, h = (LON1 - LON0) * KX, (LAT1 - LAT0) * K
    view = (0, 0, w, h)
    if region != "ALL":
        pts = [px(lat, lon) for (lat, lon), r in zip(cells, cell_regions) if r == region]
        if pts:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            pad = 2.2 * K
            x0, y0 = max(min(xs) - pad, 0), max(min(ys) - pad, 0)
            x1, y1 = min(max(xs) + pad, w), min(max(ys) + pad, h)
            side = max(x1 - x0, (y1 - y0) * 0.9)
            view = (x0, y0, side, (y1 - y0))

    out = [f'<svg id="map" viewBox="{view[0]:.0f} {view[1]:.0f} {view[2]:.0f} {view[3]:.0f}" '
           f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="Gridded map of {e(FIELDS[field][0])}">']
    out.append(f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" fill="#0b1324"/>')
    # graticule
    for lon in range(70, 99, 5):
        x = px(LAT0, lon)[0]
        out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{h:.0f}" class="gl"/>'
                   f'<text x="{x + 3:.1f}" y="{h - 6:.0f}" class="gt">{lon}°E</text>')
    for lat in range(10, 38, 5):
        y = px(lat, LON0)[1]
        out.append(f'<line x1="0" y1="{y:.1f}" x2="{w:.0f}" y2="{y:.1f}" class="gl"/>'
                   f'<text x="4" y="{y - 3:.1f}" class="gt">{lat}°N</text>')

    cw, ch = KX * STEP + 0.5, K * STEP + 0.5
    dim_attr = ' opacity="0.2"'
    for (lat, lon), val, reg in zip(cells, values, cell_regions):
        fill = colour(val)
        if fill is None:
            continue
        x, y = px(lat, lon)
        dim = region != "ALL" and reg != region
        out.append(f'<rect x="{x - cw / 2:.1f}" y="{y - ch / 2:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                   f'fill="{fill}"{dim_attr if dim else ""}/>')

    params = link_params or {}
    for row in snapshot["stations"]:
        st = row["station"]
        if region != "ALL" and st["region"] != region:
            continue
        x, y = px(st["lat"], st["lon"])
        lvl = row["alert"]["level"]
        if lead > 0:
            fc = row["forecast"][lead - 1]
            value_txt = f"Forecast day {lead}: {fc['tmax']:.1f} °C · heatwave chance {fc['p_heatwave'] * 100:.0f}%"
        else:
            value_txt = f"Tmax {row['obs']['tmax']:.1f} °C ({row['anomaly']:+.1f}) · {row['category']}"
        tip = f"{st['city']}, {st['state']} · {lvl} · {value_txt}"
        ring = ""
        if (row.get("hotspot_z") or 0) >= 1.96:
            ring = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" class="hs"/>'
        out.append(
            f'<a href="{e(url("/station/" + st["id"], **params))}" class="stn" data-tip="{e(tip)}">'
            f'{ring}<circle cx="{x:.1f}" cy="{y:.1f}" r="5.6" fill="{LEVEL_COLOURS[lvl]}" class="dot"/>'
            f'<title>{e(tip)}</title></a>')
        if st["id"] in LABELLED or region != "ALL":
            out.append(f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" class="lbl">{e(st["city"])}</text>')
    out.append("</svg>")
    return "".join(out)


def legend(field):
    if field == "watch":
        return ('<div class="legend"><span class="sw"><i style="background:#ff6a00"></i>Probable heatwave (≥60%)</span>'
                '<span class="sw"><i style="background:#f4c430"></i>Heat watch (30–60%)</span>'
                '<span class="sw"><i style="background:#1b2846;border:1px solid #2c3a5c"></i>No alert</span>'
                + _station_legend() + '</div>')
    stops = TEMP_STOPS if field == "tmax" else ANOM_STOPS
    label = "Tmax °C" if field == "tmax" else "Departure °C"
    ticks = "".join(f"<span>{v}</span>" for v, _ in stops[::2])
    return (f'<div class="legend"><span>{label}</span><div><div class="scale" style="background:{gradient_css(stops)}"></div>'
            f'<div class="ticks">{ticks}</div></div>{_station_legend()}</div>')


def _station_legend():
    dots = "".join(f'<span class="sw"><i style="background:{c};border-radius:50%"></i>{lvl.title()}</span>'
                   for lvl, c in LEVEL_COLOURS.items())
    return dots + '<span class="sw"><i class="ring"></i>Gi* hotspot</span>'
