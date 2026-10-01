"""Domain model: weather stations and observations.

Design notes:
* Class / object, default + parameterised constructor  -> WeatherStation.__init__
* Instance, class and static methods                     -> describe(), from_record(), count(), c_to_f()
* Encapsulation with a private, name-mangled attribute   -> __calibration_offset + property getter/setter
* Abstract base class with abstract methods              -> WeatherStation(ABC)
* Single / hierarchical inheritance                      -> PlainsStation, CoastalStation, HillStation
* Multilevel inheritance                                 -> WeatherStation -> PlainsStation -> DesertStation
* Multiple inheritance (mixin)                           -> WeatherStation(IoTNodeMixin, ABC)
* Polymorphism / method overriding + super()             -> heatwave_threshold(), local_risk_factors()
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

from . import science
from .config import IMD_CRITERIA
from .exceptions import InvalidStationError
from .stations_data import REGIONS, STATIONS

DESERT_STATIONS = {"WS123", "WS124", "WS125", "WS126"}


class IoTNodeMixin:
    """Behaviour shared by every IoT-enabled Automated Weather Station (AWS) node."""

    def init_node(self, battery=100.0, signal=95.0):
        self.battery = battery
        self.signal = signal

    def node_health(self):
        if self.battery < 20:
            return "LOW POWER"
        if self.signal < 30:
            return "WEAK LINK"
        return "ONLINE"


class WeatherStation(IoTNodeMixin, ABC):
    """Abstract blueprint for a heat-monitoring station."""

    station_count = 0  # class variable shared by all objects

    def __init__(self, station_id="WS000", city="Unknown", state="Unknown",
                 latitude=0.0, longitude=0.0, region="IP"):
        if region not in REGIONS:
            raise InvalidStationError(f"Unknown region '{region}' for {station_id}")
        self.station_id = station_id
        self.city = city
        self.state = state
        self.latitude = latitude
        self.longitude = longitude
        self.region = region
        self.__calibration_offset = 0.0  # private: changed only through the property
        self.init_node()
        WeatherStation.station_count += 1

    # ---- encapsulation: getter / setter -------------------------------------------
    @property
    def calibration_offset(self):
        return self.__calibration_offset

    @calibration_offset.setter
    def calibration_offset(self, value):
        if not -2.0 <= value <= 2.0:
            raise ValueError("Calibration offset must be within +/-2.0 C")
        self.__calibration_offset = value

    def calibrated(self, raw_temp):
        return round(raw_temp + self.__calibration_offset, 1)

    # ---- abstract interface (every subclass must implement) -----------------------
    @property
    @abstractmethod
    def terrain(self):
        """'plains', 'coastal' or 'hilly' - selects the IMD criterion."""

    @abstractmethod
    def local_risk_factors(self):
        """List of local factors that make heat more dangerous here."""

    # ---- polymorphic behaviour with a default implementation ----------------------
    def heatwave_threshold(self, normal_tmax, severe=False):
        """Lowest Tmax that would be classified as a (severe) heatwave today."""
        rule = IMD_CRITERIA[self.terrain]
        dep = IMD_CRITERIA["severe_departure"] + 0.1 if severe else IMD_CRITERIA["heatwave_departure"]
        return round(max(rule["min_tmax"], normal_tmax + dep), 1)

    def classify(self, tmax, normal_tmax):
        return science.imd_heatwave_category(tmax, normal_tmax, self.terrain)

    # ---- instance / class / static methods ----------------------------------------
    def describe(self):
        return (f"{self.station_id} {self.city}, {self.state} "
                f"({self.latitude:.2f}N, {self.longitude:.2f}E) - {REGIONS[self.region]}")

    @classmethod
    def from_record(cls, record):
        sid, city, state, lat, lon, region, _terrain = record
        return cls(sid, city, state, lat, lon, region)

    @classmethod
    def count(cls):
        return WeatherStation.station_count

    @staticmethod
    def c_to_f(celsius):
        return round(celsius * 9 / 5 + 32, 1)

    def lineage(self):
        """Class names from this object's class up to WeatherStation (shows the MRO)."""
        return [k.__name__ for k in type(self).__mro__
                if issubclass(k, WeatherStation)]

    def to_dict(self):
        return {
            "id": self.station_id, "city": self.city, "state": self.state,
            "lat": self.latitude, "lon": self.longitude, "region": self.region,
            "region_name": REGIONS[self.region], "terrain": self.terrain,
            "class_name": type(self).__name__, "lineage": self.lineage(),
            "risk_factors": self.local_risk_factors(),
        }

    def __str__(self):
        return f"{type(self).__name__}<{self.station_id} {self.city}>"

    __repr__ = __str__

    def __eq__(self, other):
        return isinstance(other, WeatherStation) and other.station_id == self.station_id

    def __hash__(self):
        return hash(self.station_id)

    def __lt__(self, other):
        return self.station_id < other.station_id


class PlainsStation(WeatherStation):
    @property
    def terrain(self):
        return "plains"

    def heatwave_threshold(self, normal_tmax, severe=False):
        # Plains also have absolute criteria: 45 C (heatwave) and 47 C (severe).
        base = super().heatwave_threshold(normal_tmax, severe)
        cap = IMD_CRITERIA["severe_absolute"] if severe else IMD_CRITERIA["heatwave_absolute"]
        return min(base, cap)

    def local_risk_factors(self):
        return ["Hot, dry continental air", "Urban heat island in built-up areas"]


class DesertStation(PlainsStation):
    """Thar desert station: multilevel inheritance WeatherStation -> PlainsStation -> DesertStation."""

    def local_risk_factors(self):
        return super().local_risk_factors() + ["Very low humidity, large day-night swing",
                                               "Dust storms and hot 'loo' winds"]


class CoastalStation(WeatherStation):
    @property
    def terrain(self):
        return "coastal"

    def local_risk_factors(self):
        return ["High humidity raises the heat index", "Sea breeze may fail on hot days"]


class HillStation(WeatherStation):
    @property
    def terrain(self):
        return "hilly"

    def local_risk_factors(self):
        return ["Population not acclimatised to heat", "Higher UV at altitude"]


def make_station(record):
    """Factory: pick the right subclass for a station record (polymorphic construction)."""
    sid, terrain = record[0], record[6]
    if sid in DESERT_STATIONS:
        cls = DesertStation
    else:
        cls = {"plains": PlainsStation, "coastal": CoastalStation, "hilly": HillStation}.get(terrain)
    if cls is None:
        raise InvalidStationError(f"Unknown terrain '{terrain}' for {sid}")
    return cls.from_record(record)


class StationRegistry:
    """Holds all station objects; lookups by id or region."""

    def __init__(self, records=STATIONS):
        self._stations = {r[0]: make_station(r) for r in records}

    def __iter__(self):
        return iter(sorted(self._stations.values()))

    def __len__(self):
        return len(self._stations)

    def get(self, station_id):
        try:
            return self._stations[station_id.upper()]
        except (KeyError, AttributeError):
            raise InvalidStationError(f"No station with id '{station_id}'") from None

    def by_region(self, region):
        return [s for s in self if s.region == region]


@dataclass
class DailyObservation:
    """One station-day of weather (the 'current' reading shown on the dashboard)."""

    station_id: str
    date: str
    tmax: float
    tmin: float = None
    humidity: float = None
    wind: float = None
    weather_code: int = None
    current_temp: float = None
    source: str = "replay"
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
