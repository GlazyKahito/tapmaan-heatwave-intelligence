"""HTTP routing, standard library only.

route(method, raw_path, body) -> (status, content_type, body_bytes, cache_control)
Shared by api/index.py (Vercel serverless function) and server.py (local server).

HTML pages are rendered by tapmaan.webui; /api/* returns JSON for other clients.
"""

import json
import traceback
from urllib.parse import parse_qs, unquote

from .engine import HeatwaveIntelligence
from .exceptions import InvalidStationError, TapmaanError

HTML = "text/html; charset=utf-8"


def _json(status, payload, cache=None):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return status, "application/json; charset=utf-8", body, cache


def _html(status, text, cache=None):
    return status, HTML, text.encode("utf-8"), cache


def _api(name, query):
    eng = HeatwaveIntelligence.shared()
    get = lambda k, d=None: (query.get(k) or [d])[0]  # noqa: E731
    if name == "snapshot":
        return _json(200, eng.snapshot(get("mode", "replay"), get("date")), "public, max-age=60")
    if name == "station":
        return _json(200, eng.station_detail(get("id", ""), get("mode", "replay"), get("date")))
    if name == "meta":
        return _json(200, eng.meta(), "public, max-age=600")
    if name == "validation":
        return _json(200, eng.validation(), "public, max-age=3600")
    if name == "climate":
        return _json(200, eng.climate_analysis(), "public, max-age=3600")
    if name == "health":
        return _json(200, {"ok": True})
    return _json(404, {"error": f"Unknown API endpoint '{name}'"})


def route(method, raw_path, body=b""):
    path, _, qs = raw_path.partition("?")
    query = parse_qs(qs, keep_blank_values=True)
    # Vercel rewrites every page to /api/index?__path=<original path> ("" for the home page)
    if path.rstrip("/") in ("/api/index", "/api/index.py"):
        path = "/" + (query.pop("__path", [""])[0]).lstrip("/")
    query = {k: v for k, v in query.items() if any(v)}
    path = unquote(path).rstrip("/") or "/"

    try:
        if path.startswith("/api/"):
            return _api(path[5:], query)
        if method != "GET":
            return _json(405, {"error": "Method not allowed"})

        from .webui import pages  # imported lazily: keeps the JSON API light
        p = pages.Params(query)
        partial = "partial" in query
        cache = "public, max-age=30, s-maxage=60" if p.mode != "live" else "public, max-age=60"
        if path == "/":
            return _html(200, pages.watch_page(p, partial), cache)
        if path.startswith("/station/"):
            html = pages.station_page(p, path.split("/")[2])
            return _html(200, html, cache) if html else _html(404, pages.not_found_page())
        simple = {"/warnings": pages.warnings_page, "/skill": pages.skill_page, "/climate": pages.climate_page,
                  "/aws": pages.aws_page, "/data": pages.data_page, "/about": pages.about_page}
        if path in simple:
            no_cache = path in ("/aws", "/data")
            return _html(200, simple[path](p), None if no_cache else cache)
        return _html(404, pages.not_found_page())
    except InvalidStationError as err:
        return _json(404, {"error": str(err)}) if path.startswith("/api/") else _html(404, _error_page(str(err)))
    except TapmaanError as err:
        return _json(422, {"error": str(err)}) if path.startswith("/api/") else _html(422, _error_page(str(err)))
    except Exception as err:  # never show a raw stack trace to visitors
        traceback.print_exc()
        msg = f"Internal error: {type(err).__name__}"
        return _json(500, {"error": msg}) if path.startswith("/api/") else _html(500, _error_page(msg))


def _error_page(message):
    from .webui.html import e, page
    return page("Error", f'<div class="page-head"><div><div class="eyebrow">Something went wrong</div><h1>{e(message)}</h1>'
                         f'<p><a href="/">Back to the Heatwave Watch →</a></p></div></div>', "", "", "replay")
