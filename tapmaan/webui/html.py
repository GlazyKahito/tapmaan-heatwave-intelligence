"""HTML building blocks: page shell, navigation and small reusable components.

Every page of the website is produced by Python functions that return strings.
"""

from html import escape
from urllib.parse import urlencode

from ..config import ALERT_META, APP_NAME, APP_TAGLINE, USE_CASE_ID
from ..logo import to_svg

NAV = [
    ("/", "Heatwave Watch"),
    ("/warnings", "Early Warnings"),
    ("/scenarios", "Scenario Lab"),
    ("/skill", "Forecast Skill"),
    ("/climate", "Climate Trends"),
    ("/aws", "AWS Network"),
    ("/data", "Data Explorer"),
    ("/about", "About"),
]
LEVEL_COLOURS = {k: v["colour"] for k, v in ALERT_META.items()}


def e(value):
    """Escape any value for HTML."""
    return escape("" if value is None else str(value), quote=True)


def url(path, **params):
    clean = {k: v for k, v in params.items() if v not in (None, "", False)}
    return path + ("?" + urlencode(clean) if clean else "")


def fmt(value, digits=1, unit=""):
    if value is None:
        return "–"
    return f"{value:.{digits}f}{unit}"


def signed(value, digits=1):
    return "–" if value is None else f"{value:+.{digits}f}"


def pct(value, digits=0):
    return "–" if value is None else f"{value * 100:.{digits}f}%"


def badge(level):
    return f'<span class="badge {e(level)}">{e(level)}</span>'


def cat_class(category):
    if category.startswith("SEVERE"):
        return "cat-SEVERE"
    return "cat-HEATWAVE" if category == "HEATWAVE" else "cat-NORMAL"


def kpi(value, label, tone=""):
    return f'<div class="kpi {tone}"><div class="v num">{e(value)}</div><div class="k">{e(label)}</div></div>'


def stat(label, value, sub=""):
    return (f'<div class="stat"><span class="k">{e(label)}</span><span class="v num">{value}</span>'
            f'{f"<span class=s>{sub}</span>" if sub else ""}</div>')


def card(body, title="", hint="", cls=""):
    head = (f'<div class="card-title"><h3>{title}</h3>{f"<span class=hint>{hint}</span>" if hint else ""}</div>'
            if title else "")
    return f'<section class="card {cls}">{head}{body}</section>'


def table(headers, rows, cls="", row_links=None):
    """headers: list of (label, css_class); rows: list of lists of HTML cells."""
    head = "".join(f'<th class="{c}">{e(h)}</th>' for h, c in headers)
    body = []
    for i, r in enumerate(rows):
        link = row_links[i] if row_links else None
        attrs = f' class="click" data-href="{e(link)}"' if link else ""
        cells = "".join(f'<td class="{headers[j][1]}">{c}</td>' for j, c in enumerate(r))
        body.append(f"<tr{attrs}>{cells}</tr>")
    return f'<div class="table-wrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def seg(options, current, make_href, hot=None):
    """Segmented control made of links. options: [(value, label)]."""
    out = []
    for value, label in options:
        cls = "on" + (" hot" if hot and value == current else "") if value == current else ""
        out.append(f'<a class="{cls}" href="{e(make_href(value))}" data-nav>{e(label)}</a>')
    return f'<div class="seg">{"".join(out)}</div>'


def notice(text, kind="info"):
    return f'<div class="notice {kind}">{text}</div>'


def page(title, body, active="/", mode_label="", mode="replay", description=""):
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">{e(label)}</a>' for href, label in NAV)
    pill_cls = "mode-pill live" if mode == "live" else "mode-pill"
    desc = description or (f"{APP_NAME} {APP_TAGLINE}: heatwave monitoring, prediction and early warning "
                           "for 50 Indian stations with explainable forecasts and stakeholder advisories.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} · {APP_NAME}</title>
<meta name="description" content="{e(desc)}">
<meta name="theme-color" content="#f3ead7">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Source+Sans+3:wght@400;600;700&family=Courier+Prime&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/app.css">
</head>
<body>
<header class="topbar">
  <a class="brand" href="/">
    <img class="brand-mark" src="/favicon.svg" alt="">
    <span class="brand-text"><b>{APP_NAME}</b><small>{APP_TAGLINE}</small></span>
  </a>
  <nav class="nav">{nav}</nav>
  <div class="clock" title="Indian Standard Time">
    <b data-clock>--:--:-- IST</b>
    <span><span class="{pill_cls}" data-pill><span class="dot"></span>{e(mode_label)}</span></span>
  </div>
</header>
<main class="view" id="main">
{body}
</main>
<footer class="footer">
  <span>{APP_NAME} · {USE_CASE_ID} Climate Intelligence for Heatwave Monitoring, Prediction &amp; Early Warning · <a href="/?intro=1">replay intro</a></span>
  <span>Research prototype, not an official forecast. Official warnings: <a href="https://mausam.imd.gov.in" target="_blank" rel="noopener">mausam.imd.gov.in</a></span>
</footer>
<div id="tooltip" class="tooltip" hidden></div>
<div class="toasts" id="toasts" aria-live="polite"></div>
<script src="/js/enhance.js" defer></script>
</body>
</html>"""


def logo_svg(scale=1.0):
    return to_svg(scale)
