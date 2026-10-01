"""Heat-stress science used across Tapmaan (pure functions, standard library only).

* IMD heatwave criteria (plains / coastal / hilly stations)
* NOAA heat index (Rothfusz regression with the standard adjustments)
* Wet-bulb temperature (Stull, 2011)
"""

import math

from .config import IMD_CRITERIA

NORMAL, HEATWAVE, SEVERE = "NORMAL", "HEATWAVE", "SEVERE HEATWAVE"


def celsius_to_fahrenheit(c):
    return c * 9 / 5 + 32


def fahrenheit_to_celsius(f):
    return (f - 32) * 5 / 9


def imd_heatwave_category(tmax, normal_tmax, terrain="plains"):
    """Classify a day using the IMD heatwave definition.

    A heatwave needs the station to reach a terrain-specific threshold
    (plains 40 C, coastal 37 C, hilly 30 C) and then either:
      * departure from normal 4.5-6.4 C  -> HEATWAVE, > 6.4 C -> SEVERE HEATWAVE
      * (plains) actual Tmax >= 45 C     -> HEATWAVE, >= 47 C -> SEVERE HEATWAVE
    """
    rule = IMD_CRITERIA[terrain]
    if tmax is None or normal_tmax is None or tmax < rule["min_tmax"]:
        return NORMAL
    departure = tmax - normal_tmax
    category = NORMAL
    if departure > IMD_CRITERIA["severe_departure"]:
        category = SEVERE
    elif departure >= IMD_CRITERIA["heatwave_departure"]:
        category = HEATWAVE
    if terrain == "plains":
        if tmax >= IMD_CRITERIA["severe_absolute"]:
            category = SEVERE
        elif tmax >= IMD_CRITERIA["heatwave_absolute"] and category == NORMAL:
            category = HEATWAVE
    return category


def heat_index_c(temp_c, rh):
    """NOAA heat index (apparent temperature) in Celsius."""
    t = celsius_to_fahrenheit(temp_c)
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if (simple + t) / 2 < 80:
        return round(fahrenheit_to_celsius(simple), 1)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
          - 6.83783e-3 * t * t - 5.481717e-2 * rh * rh + 1.22874e-3 * t * t * rh
          + 8.5282e-4 * t * rh * rh - 1.99e-6 * t * t * rh * rh)
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return round(fahrenheit_to_celsius(hi), 1)


def heat_index_band(hi_c):
    if hi_c >= 54:
        return "Extreme Danger"
    if hi_c >= 41:
        return "Danger"
    if hi_c >= 32:
        return "Extreme Caution"
    if hi_c >= 27:
        return "Caution"
    return "Comfortable"


def wet_bulb_c(temp_c, rh):
    """Stull (2011) empirical wet-bulb temperature, valid for RH 5-99 % and -20..50 C."""
    rh = min(max(rh, 5), 99)
    tw = (temp_c * math.atan(0.151977 * math.sqrt(rh + 8.313659))
          + math.atan(temp_c + rh) - math.atan(rh - 1.676331)
          + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)
    return round(tw, 1)


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
