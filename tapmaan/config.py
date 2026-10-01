"""Every threshold, weight and constant in one place."""

APP_NAME = "Tapmaan"
APP_TAGLINE = "Heatwave Intelligence Grid"
USE_CASE_ID = "KJS-CES-01"

# IMD heatwave definition
IMD_CRITERIA = {
    "plains": {"min_tmax": 40.0},
    "coastal": {"min_tmax": 37.0},
    "hilly": {"min_tmax": 30.0},
    "heatwave_departure": 4.5,
    "severe_departure": 6.4,
    "heatwave_absolute": 45.0,
    "severe_absolute": 47.0,
}

# Impact-based colour codes used in IMD warnings
ALERT_LEVELS = ("GREEN", "YELLOW", "ORANGE", "RED")
ALERT_META = {
    "GREEN": {"label": "No Action", "colour": "#5b7a4b", "meaning": "Normal day. No heat warning."},
    "YELLOW": {"label": "Be Updated", "colour": "#c4962a", "meaning": "Heat watch. Stay alert, keep updated."},
    "ORANGE": {"label": "Be Prepared", "colour": "#c0661d", "meaning": "Heatwave alert. Protect vulnerable groups."},
    "RED": {"label": "Take Action", "colour": "#8e2a1e", "meaning": "Severe heatwave warning. Take action now."},
}

# Early warning engine: score weights (sum = 1.0)
RISK_WEIGHTS = {
    "imd_severity": 0.35,
    "forecast_probability": 0.25,
    "heat_index": 0.20,
    "wet_bulb": 0.10,
    "persistence": 0.10,
}
LEVEL_CUTOFFS = ((70, "RED"), (45, "ORANGE"), (22, "YELLOW"))

# Forecasting
FORECAST_HORIZON = 5
FORECAST_HISTORY_DAYS = 14
HOLT_ALPHAS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
HOLT_BETAS = (0.05, 0.1, 0.2, 0.3)
HOLT_PHI = 0.85          # damping of the trend
CLIMATOLOGY_PULL = 0.18  # how strongly each extra lead day relaxes toward normal

# Map / hotspot analysis
GRID_STEP_DEG = 0.5      # twice as fine as the IMD 1-degree gridded dataset
GRID_LAT = (6.5, 37.5)
GRID_LON = (67.5, 97.5)
IDW_POWER = 2
IDW_MAX_KM = 300
HOTSPOT_BAND_KM = 450

# Live data
LIVE_CACHE_SECONDS = 600
HTTP_TIMEOUT = 8
LIVE_CHUNK_SIZE = 10

# Data Explorer
SQL_MAX_ROWS = 200
