"""Phase I - Meteorological data acquisition (offline build step).

Downloads ERA5 reanalysis daily maximum temperature from the Open-Meteo archive API
and condenses it into two compact JSON files that ship with the app:

* tapmaan/data/climatology.json - per station: smoothed day-of-year normal Tmax
  (1995-2024), monthly mean Tmax for every year, and IMD heatwave days per year.
* tapmaan/data/replay_2024.json - daily Tmax / Tmin / RH / wind for the real
  April-June 2024 heatwave, used by the Replay mode and the forecast backtests.

Run:  python scripts/build_datasets.py
ERA5 stands in for the IMD 1-degree gridded Tmax files (see tapmaan/grd_reader.py).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tapmaan.stations_data import STATIONS  # noqa: E402
from tapmaan.science import imd_heatwave_category  # noqa: E402

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
CLIM_START, CLIM_END = "1995-01-01", "2024-12-31"
REPLAY_START, REPLAY_END = "2024-04-10", "2024-06-25"
OUT_DIR = os.path.join(ROOT, "tapmaan", "data")


def fetch(params, retries=6):
    url = ARCHIVE + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as err:
            wait = 20 * (attempt + 1) if err.code == 429 else 5
            print(f"  HTTP {err.code}, retrying in {wait}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as err:
            print(f"  network error {err}, retrying", flush=True)
            time.sleep(5)
    raise RuntimeError("giving up on " + url)


def smooth_circular(values, window=15):
    n, half = len(values), window // 2
    return [sum(values[(i + k) % n] for k in range(-half, half + 1)) / window for i in range(n)]


def build_climatology():
    out = {}
    for sid, city, *_rest in STATIONS:
        lat, lon, terrain = _rest[1], _rest[2], _rest[4]
        print(f"climatology {sid} {city}", flush=True)
        data = fetch({
            "latitude": lat, "longitude": lon, "start_date": CLIM_START, "end_date": CLIM_END,
            "daily": "temperature_2m_max", "timezone": "Asia/Kolkata",
        })
        days, tmax = data["daily"]["time"], data["daily"]["temperature_2m_max"]

        by_doy = defaultdict(list)
        monthly = defaultdict(list)
        for d, t in zip(days, tmax):
            if t is None:
                continue
            dt = date.fromisoformat(d)
            doy = min(dt.timetuple().tm_yday, 365) - 1
            by_doy[doy].append(t)
            monthly[(dt.year, dt.month)].append(t)
        raw = [sum(by_doy[i]) / len(by_doy[i]) for i in range(365)]
        normal = [round(v, 2) for v in smooth_circular(raw)]

        years = sorted({y for y, _ in monthly})
        monthly_means = {
            str(y): [round(sum(monthly[(y, m)]) / len(monthly[(y, m)]), 2) if monthly[(y, m)] else None
                     for m in range(1, 13)]
            for y in years
        }
        hw_days = defaultdict(int)
        for d, t in zip(days, tmax):
            if t is None:
                continue
            dt = date.fromisoformat(d)
            doy = min(dt.timetuple().tm_yday, 365) - 1
            if imd_heatwave_category(t, normal[doy], terrain) != "NORMAL":
                hw_days[dt.year] += 1
        out[sid] = {
            "elevation": data.get("elevation"),
            "normal_tmax_doy": normal,
            "monthly_mean_tmax": monthly_means,
            "heatwave_days": {str(y): hw_days.get(y, 0) for y in years},
        }
        time.sleep(4)
    return {"source": "ERA5 via Open-Meteo archive API", "period": [CLIM_START, CLIM_END], "stations": out}


def build_replay():
    lats = ",".join(str(s[3]) for s in STATIONS)
    lons = ",".join(str(s[4]) for s in STATIONS)
    print("replay 2024 (all stations)", flush=True)
    data = fetch({
        "latitude": lats, "longitude": lons, "start_date": REPLAY_START, "end_date": REPLAY_END,
        "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_min,wind_speed_10m_max,weather_code",
        "timezone": "Asia/Kolkata",
    })
    out = {}
    for (sid, *_), loc in zip(STATIONS, data):
        d = loc["daily"]
        out[sid] = {
            "tmax": d["temperature_2m_max"], "tmin": d["temperature_2m_min"],
            "rh": d["relative_humidity_2m_min"], "wind": d["wind_speed_10m_max"],
            "code": d["weather_code"],
        }
    return {"source": "ERA5 via Open-Meteo archive API", "dates": data[0]["daily"]["time"], "stations": out}


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "replay"):
        with open(os.path.join(OUT_DIR, "replay_2024.json"), "w") as f:
            json.dump(build_replay(), f, separators=(",", ":"))
    if what in ("all", "climatology"):
        with open(os.path.join(OUT_DIR, "climatology.json"), "w") as f:
            json.dump(build_climatology(), f, separators=(",", ":"))
    print("done")
