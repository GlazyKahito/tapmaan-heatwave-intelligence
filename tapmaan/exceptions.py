"""Custom exception hierarchy.

Every error raised by Tapmaan derives from TapmaanError so a caller can catch the whole
family with one except clause, or catch a precise subclass when it can recover.
"""


class TapmaanError(Exception):
    """Base class for all Tapmaan errors."""


class InvalidStationError(TapmaanError):
    """Unknown station id or malformed station record."""


class SensorError(TapmaanError):
    """Base class for problems with an AWS sensor reading."""

    def __init__(self, station_id, parameter, message):
        super().__init__(f"[{station_id}] {parameter}: {message}")
        self.station_id = station_id
        self.parameter = parameter


class InvalidSensorValueError(SensorError):
    """A reading is outside the physically possible range (e.g. humidity 137 %)."""


class WeatherDataUnavailableError(SensorError):
    """The sensor returned no data (missing value)."""


class SensorCommunicationError(SensorError):
    """The AWS node did not answer in time (communication failure)."""


class DataSourceError(TapmaanError):
    """A whole data provider failed (network down, bad payload...)."""


class ForecastError(TapmaanError):
    """Not enough clean history to fit the forecasting model."""


class QueryNotAllowedError(TapmaanError):
    """The Data Explorer received a statement that is not a read-only SELECT."""


class GridFileError(TapmaanError):
    """An IMD .grd file has the wrong size or cannot be read."""
