# Tapmaan · तापमान — Heatwave Intelligence Grid

**Heatwave monitoring, prediction and early warning for India**, built around use case
**KJS-CES-01: Climate Intelligence for Heatwave Monitoring, Prediction, and Early Warning**
(collaborating organisation: India Meteorological Department, Mumbai–Pune).

Tapmaan follows 50 stations across India's seven temperature-homogeneous regions. It forecasts
maximum temperature up to five days ahead, classifies heatwaves with the official IMD criteria,
finds statistically significant hotspots and turns all of it into advisories for citizens, farmers,
health departments and local authorities.

It runs in two forms on one Python core:

| | |
|---|---|
| **Website** | Every page, the gridded India heat map and all charts are rendered **by Python** (standard-library HTTP handler + Matplotlib/Seaborn) and deployed on Vercel. |
| **Desktop** | **Heatwave Operations Console**, a multi-screen Tkinter app with embedded Matplotlib charts and threaded data loading (`python desktop.py`). |

> Research prototype. Official heat warnings are issued only by IMD at <https://mausam.imd.gov.in>.

---

## Highlights

* **Replay the real May 2024 heatwave.** ERA5 data for April–June 2024. Press *Play* and watch the heat build
  over Rajasthan, Uttar Pradesh and Madhya Pradesh (Banda 48.6 °C on 28 May).
* **Live mode.** Today's data for all 50 stations from the Open-Meteo API, fetched by parallel threads.
  If the network fails, the app falls back to simulated data station by station.
* **An AI forecaster that beats the baseline.** A pooled ridge regression is retrained every day on all stations.
  In a walk-forward backtest over 11,500 forecasts it beats persistence ("tomorrow = today") at every lead time.
* **IMD-faithful severity.** The plains, coastal and hill criteria, departure-from-normal rules and absolute
  45 °C / 47 °C rules are all applied, with normals from 30 years of data (1995–2024).
* **Hotspots with statistics, not eyeballing.** Getis-Ord Gi\* z-scores. A station is a hotspot only when its
  neighbourhood is significantly hotter than normal (z ≥ 1.96).
* **Explainable early warnings.** A weighted risk score from five named rules, IMD impact colours
  (Green / Yellow / Orange / Red) and a plain-English "Why this alert?".
* **Advisories with a human in the loop.** Each audience gets its own actions. A fact checker verifies every
  quoted temperature. ORANGE and RED advisories stay drafts until a meteorologist approves them.
* **Multilingual dissemination.** SMS in English, हिन्दी and मराठी with correct GSM-7 / UCS-2 segment
  counting, plus a formatted bulletin.
* **IoT AWS network simulator.** Temperature, humidity and wind threads poll the stations concurrently over a lossy link.
  Timeouts, missing packets and impossible values are caught per reading and shown on a thread timeline.
* **Scenario Lab.** Inject a heat dome, monsoon onset, humidity surge or urban heat island and watch the
  warning system react: escalations, de-escalations, and direct versus indirect (model-coupled) effects.
* **Start-up sequence and live touches.** The start-up screen reports real pipeline numbers. The site also has
  an IST clock, an alert ticker, a "since yesterday" feed with escalation toasts during Play, a scan sweep on
  the map, a coordinate readout and keyboard control.
* **Data Explorer.** The snapshot is loaded into SQLite. Saved queries cover JOIN, GROUP BY, HAVING and more, and
  a guarded editor allows SELECT only.

## Forecast skill (2024 backtest, 50 stations, 1 May – 15 Jun)

| Lead | Model MAE | Persistence MAE | Climatology MAE | Skill vs persistence |
|---|---|---|---|---|
| Day 1 | 1.22 °C | 1.23 °C | 2.54 °C | +0.8 % |
| Day 2 | 1.60 °C | 1.66 °C | 2.56 °C | +3.6 % |
| Day 3 | 1.91 °C | 1.98 °C | 2.59 °C | +3.5 % |
| Day 4 | 2.12 °C | 2.24 °C | 2.60 °C | +5.4 % |
| Day 5 | 2.30 °C | 2.46 °C | 2.60 °C | +6.5 % |

Day-1 heatwave detection: POD 0.55, FAR 0.19, CSI 0.48. The live *Forecast Skill* page recomputes all of this.

## Architecture

The five layers mirror the use-case conceptual schema.

```
 1  DATA ACQUISITION   providers.py     Replay (ERA5 2024) · Live (Open-Meteo, threaded) · Simulated
                       climatology.py   30-year day-of-year normals, monthly means, heatwave-day counts
                       grd_reader.py    reader for IMD 1° gridded Tmax (.grd) files
 2  ANALYTICS          spatial.py       0.5° IDW grid · region aggregation
                       analytics.py     7 regions × 4 seasons · trends · national statistics
 3  AI INTELLIGENCE    forecast.py      regional ridge forecaster (+ damped-Holt fallback), probabilities
                       alerts.py        IMD severity + explainable early-warning engine
                       spatial.py       Getis-Ord Gi* hotspot detection
 4  VALIDATION         validation.py    walk-forward backtest · MAE/RMSE/bias · POD/FAR/CSI/Brier
 5  DECISION SUPPORT   advisories.py    stakeholder advisors · fact checker · SMS/bulletin channels
                       engine.py        HeatwaveIntelligence facade that runs the pipeline
                       scenarios.py     what-if scenarios (Scenario ABC -> four concrete scenarios)
    INTERFACES         webui/           Python-rendered pages, SVG map, Matplotlib/Seaborn charts
                       web.py           router (pages + JSON API) · api/index.py (Vercel handler)
                       desktop.py       Tkinter Heatwave Operations Console
                       database.py      SQLite repository + read-only query guard
                       aws_network.py   threaded IoT sensor network simulator
```

### The forecasting model

For each lead day *h* = 1…5, a separate ridge regression predicts the **anomaly** (Tmax minus the station
normal) from three features:

```
anomaly(t+h) = w1·anomaly(t) + w2·[anomaly(t) − anomaly(t−1)] + w3·regional_anomaly(t) + b
```

It is pooled across all 50 stations (about 600 samples) and trained only on the last 14 days, so it relearns
every day. It never sees future data. The spread of the training residuals gives a normal distribution for
each lead, which turns the forecast into `P(heatwave)` and `P(severe heatwave)` against each station's own IMD threshold.

### Early-warning score

| Rule | Weight |
|---|---|
| Observed IMD severity | 0.35 |
| AI forecast probability (next 72 h) | 0.25 |
| Heat index (NOAA) | 0.20 |
| Wet-bulb temperature (Stull) | 0.10 |
| Persistence (consecutive heatwave days) | 0.10 |

Score ≥ 70 → RED, ≥ 45 → ORANGE, ≥ 22 → YELLOW. Hard overrides apply: an observed severe heatwave
forces RED, an observed heatwave forces at least ORANGE, and a wet-bulb temperature ≥ 31 °C forces at least ORANGE.

## Object-oriented design

* `WeatherStation` (abstract base class) → `PlainsStation` → `DesertStation`, plus `CoastalStation` and
  `HillStation`. Each overrides `terrain`, `local_risk_factors()` and `heatwave_threshold()`. An `IoTNodeMixin`
  adds AWS node behaviour. The private calibration offset is reachable only through a validated property.
* `WeatherProvider` (ABC) → `ReplayProvider`, `LiveProvider`, `SimulatedProvider`, plus `ResilientProvider`, which composes a primary and a fallback provider.
* `StakeholderAdvisor` (ABC) → citizen, farmer, health and authority advisors. `AdvisoryGenerator` (ABC) →
  `TemplateAdvisoryGenerator`. An LLM-backed generator can plug into the same interface.
* `AlertChannel` (ABC) → `SMSChannel` → `HindiSMSChannel` / `MarathiSMSChannel`, plus `BulletinChannel`.
* `SensorMonitor(threading.Thread)` → temperature, humidity and wind monitors.
* Custom exception hierarchy rooted at `TapmaanError` (sensor, data-source, forecast, query and grid errors).

## Run it

Requires Python 3.10+.

```bash
git clone https://github.com/GlazyKahito/tapmaan-heatwave-intelligence.git
cd tapmaan-heatwave-intelligence
pip install -r requirements.txt

python server.py          # website on http://localhost:8000
python desktop.py         # Tkinter Heatwave Operations Console
python -m pytest -q       # 39 tests
```

The core runs on the standard library alone; NumPy, Pandas, Matplotlib and Seaborn are used for the charts.
Live mode needs internet access; replay and simulated modes work offline.

To rebuild the bundled datasets (downloads about 30 years of ERA5 data, takes a few minutes):

```bash
python scripts/build_datasets.py
```

## Pages

| Page | What it shows |
|---|---|
| **Heatwave Watch** | Gridded map (Tmax, departure, heatwave-watch probability), observed or day 1–5 forecast, national or regional zoom, alert counts, hottest and most anomalous stations, region cards, today's model weights |
| **Station** | 14-day history and 5-day forecast with 80 % interval and verification, "Why this alert?", outlook table, four stakeholder advisories with approve/reject, SMS in three languages, bulletin, seasonal cycle |
| **Early Warnings** | Every station ranked by risk score, filters by level and region, generated national bulletin, approval queue |
| **Scenario Lab** | What-if stress tests (heat dome, monsoon onset, humidity surge, urban heat island). The whole pipeline re-runs on a perturbed copy of the data and shows which stations escalate, and why |
| **Forecast Skill** | Walk-forward verification against persistence and climatology, event scores, error by region |
| **Climate Trends** | Seaborn region × season heatmap, pre-monsoon trends by region, heatwave days per year with trend |
| **AWS Network** | Concurrent sensor sweep, Matplotlib thread timeline, exception log, threshold warnings |
| **Data Explorer** | SQLite `stations` and `readings` tables, saved queries, read-only SQL editor |
| **About** | Architecture, IMD criteria, AI governance, data sources, limitations |

JSON API: `/api/snapshot`, `/api/station?id=WS101`, `/api/validation`, `/api/climate`, `/api/meta`
(add `mode=replay|live|simulated` and `date=YYYY-MM-DD` where relevant).

## Project structure

```
api/index.py            Vercel serverless entry (BaseHTTPRequestHandler)
server.py               local web server
desktop.py              Tkinter Heatwave Operations Console
tapmaan/                core package (see Architecture)
  data/                 climatology.json (1995–2024) · replay_2024.json
  webui/                html.py · mapsvg.py · charts.py · pages.py
public/                 css, small progressive-enhancement JS, favicon
scripts/build_datasets.py   data acquisition pipeline
tests/test_core.py      unit + route tests
```

## Data and limitations

* ERA5 reanalysis (via the Open-Meteo archive API) stands in for IMD station data. Reanalysis is smoother, so peak
  temperatures run 1–3 °C below station observations. Thresholds still use each station's own ERA5 normal.
* The forecaster learns from temperature history only. It has no physics from a numerical weather model.
* The AWS network is simulated; no real hardware is polled.
* The station-to-region mapping is approximate.
* Advisories are template-based. Approvals are stored in the browser that made them.
