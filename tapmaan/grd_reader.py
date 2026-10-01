"""Reader for IMD 1-degree gridded maximum-temperature (.grd) files.

IMD Pune publishes daily Tmax on a 31 x 31 grid (1 degree, 7.5N-37.5N, 67.5E-97.5E) as
raw little-endian float32 values, one grid per day, with 99.9 marking missing cells.
This reader lets the same pipeline ingest those files (Phase I). The bundled demo uses ERA5
data instead because IMD files require a manual download from imdpune.gov.in.
"""

import os
import struct

from .exceptions import GridFileError

NLAT = NLON = 31
LAT0, LON0, STEP = 7.5, 67.5, 1.0
MISSING = 99.9
CELL_BYTES = 4


class IMDGridReader:
    def __init__(self, path):
        self.path = path
        try:
            size = os.path.getsize(path)
        except OSError as err:
            raise GridFileError(f"Cannot open {path}: {err}") from err
        per_day = NLAT * NLON * CELL_BYTES
        if size == 0 or size % per_day:
            raise GridFileError(f"{path}: size {size} is not a multiple of one day ({per_day} bytes)")
        self.days = size // per_day

    def read_day(self, day):
        """Return a 31x31 list of lists [lat][lon]; missing cells are None."""
        if not 0 <= day < self.days:
            raise GridFileError(f"Day {day} out of range 0..{self.days - 1}")
        per_day = NLAT * NLON
        with open(self.path, "rb") as f:
            f.seek(day * per_day * CELL_BYTES)
            values = struct.unpack(f"<{per_day}f", f.read(per_day * CELL_BYTES))
        return [[None if abs(v - MISSING) < 0.01 else round(v, 2)
                 for v in values[r * NLON:(r + 1) * NLON]] for r in range(NLAT)]

    def value_at(self, lat, lon, day):
        r, c = round((lat - LAT0) / STEP), round((lon - LON0) / STEP)
        if not (0 <= r < NLAT and 0 <= c < NLON):
            raise GridFileError(f"({lat}, {lon}) is outside the IMD grid")
        return self.read_day(day)[r][c]

    @staticmethod
    def write(path, grids):
        """Write grids (list of 31x31 lists, None = missing) in IMD format - used by tests."""
        with open(path, "wb") as f:
            for grid in grids:
                flat = [MISSING if v is None else v for row in grid for v in row]
                f.write(struct.pack(f"<{len(flat)}f", *flat))
