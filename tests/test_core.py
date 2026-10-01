"""Unit tests for the Tapmaan core. Run with:  python -m pytest -q"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tapmaan import science  # noqa: E402
from tapmaan.advisories import FactChecker, SMSChannel, disseminate  # noqa: E402
from tapmaan.alerts import EarlyWarningEngine  # noqa: E402
from tapmaan.aws_network import AWSNetwork  # noqa: E402
from tapmaan.database import ClimateDatabase  # noqa: E402
from tapmaan.engine import HeatwaveIntelligence  # noqa: E402
from tapmaan.exceptions import ForecastError, GridFileError, InvalidStationError, QueryNotAllowedError  # noqa: E402
from tapmaan.forecast import HoltDampedModel, solve_linear  # noqa: E402
from tapmaan.grd_reader import IMDGridReader  # noqa: E402
from tapmaan.models import (CoastalStation, DesertStation, HillStation, PlainsStation, StationRegistry,  # noqa: E402
                            WeatherStation)


@pytest.fixture(scope="module")
def engine():
    return HeatwaveIntelligence.shared()


@pytest.fixture(scope="module")
def snap(engine):
    return engine.snapshot("replay", "2024-05-28")


# ---------------------------------------------------------------- science
@pytest.mark.parametrize("tmax,normal,terrain,expected", [
    (39.9, 30.0, "plains", science.NORMAL),        # below 40 C: never a heatwave on plains
    (44.0, 39.0, "plains", science.HEATWAVE),      # departure 5.0
    (46.0, 39.0, "plains", science.SEVERE),        # departure 7.0
    (45.2, 43.0, "plains", science.HEATWAVE),      # absolute criterion
    (47.0, 46.0, "plains", science.SEVERE),        # absolute severe
    (38.0, 32.0, "coastal", science.HEATWAVE),     # coastal threshold is 37 C, departure 6.0
    (39.0, 32.0, "coastal", science.SEVERE),       # departure 7.0
    (31.0, 26.0, "hilly", science.HEATWAVE),       # hilly threshold is 30 C
    (38.0, 32.0, "plains", science.NORMAL),
])
def test_imd_criteria(tmax, normal, terrain, expected):
    assert science.imd_heatwave_category(tmax, normal, terrain) == expected


def test_heat_index_and_wet_bulb():
    assert science.heat_index_c(25, 50) < 27                 # mild day stays mild
    assert science.heat_index_c(35, 70) > 45                 # humid heat is dangerous
    assert 25 < science.wet_bulb_c(35, 60) < 30
    assert science.wet_bulb_c(20, 100) == pytest.approx(20, abs=0.6)


# ---------------------------------------------------------------- OOP model
def test_abstract_station_cannot_be_created():
    with pytest.raises(TypeError):
        WeatherStation("WS000", "Nowhere")


def test_factory_builds_correct_subclasses():
    reg = StationRegistry()
    assert len(reg) == 50
    assert isinstance(reg.get("WS125"), DesertStation)
    assert isinstance(reg.get("WS125"), PlainsStation)       # multilevel inheritance
    assert isinstance(reg.get("WS102"), CoastalStation)
    assert isinstance(reg.get("WS131"), HillStation)
    assert reg.get("ws101").city == "Pune"
    with pytest.raises(InvalidStationError):
        reg.get("WS999")


def test_calibration_offset_is_validated():
    st = StationRegistry().get("WS101")
    st.calibration_offset = 0.5
    assert st.calibrated(30.0) == 30.5
    with pytest.raises(ValueError):
        st.calibration_offset = 5


def test_polymorphic_thresholds():
    reg = StationRegistry()
    assert reg.get("WS103").heatwave_threshold(42.0) == 45.0        # absolute 45 C rule applies first
    assert reg.get("WS103").heatwave_threshold(38.0) == 42.5
    assert reg.get("WS103").heatwave_threshold(42.0, severe=True) == 47.0   # capped by absolute rule
    assert reg.get("WS102").heatwave_threshold(31.0) == 37.0
    assert reg.get("WS131").heatwave_threshold(24.0) == 30.0


# ---------------------------------------------------------------- forecasting
def test_solve_linear():
    assert solve_linear([[2, 1], [1, 3]], [3, 5]) == pytest.approx([0.8, 1.4])


def test_holt_needs_history():
    with pytest.raises(ForecastError):
        HoltDampedModel.best_fit([1.0, None, 2.0])


def test_forecasts_are_probabilistic(snap):
    for row in snap["stations"]:
        assert len(row["forecast"]) == 5
        for day in row["forecast"]:
            assert 0 <= day["p_severe"] <= day["p_heatwave"] <= 1
            assert day["lo"] <= day["tmax"] <= day["hi"]


def test_model_beats_persistence(engine):
    val = engine.validation()
    for lead in val["leads"]:
        assert lead["model"]["mae"] <= lead["persistence"]["mae"] + 0.01
        assert lead["model"]["mae"] < lead["climatology"]["mae"]


# ---------------------------------------------------------------- alerts & snapshot
def test_severe_heatwave_forces_red():
    result = EarlyWarningEngine().assess(science.SEVERE, 7.0, [{"p_heatwave": 0, "p_severe": 0}] * 3, 30, 20, 0)
    assert result["level"] == "RED"


def test_snapshot_shape(snap):
    assert len(snap["stations"]) == 50
    assert sum(snap["summary"]["levels"].values()) == 50
    assert {r["code"] for r in snap["regions"]} == {"WH", "NW", "NC", "NE", "WC", "EC", "IP"}
    banda = next(r for r in snap["stations"] if r["station"]["id"] == "WS119")
    assert banda["category"] == science.SEVERE and banda["alert"]["level"] == "RED"
    assert banda["hotspot_z"] >= 1.96


# ---------------------------------------------------------------- advisories
def test_fact_checker_catches_wrong_numbers():
    ctx = {"tmax": 45.0, "normal": 40.0, "peak_tmax": 46.0, "heat_index": 47.0, "wet_bulb": 25.0}
    assert FactChecker().verify("Max 45.0 °C, normal 40.0 °C", ctx)["passed"]
    assert not FactChecker().verify("Max 49.0 °C", ctx)["passed"]


def test_sms_channels(engine):
    d = engine.station_detail("WS125", "replay", "2024-05-28")
    msgs = disseminate(engine.advisory_context(d))
    assert len(SMSChannel().render(engine.advisory_context(d))) <= 160
    assert msgs[1]["encoding"] == "UCS-2"                 # Hindi needs Unicode SMS
    assert all(a["fact_check"]["passed"] for a in d["advisories"])


# ---------------------------------------------------------------- threads
def test_aws_sweep_is_concurrent_and_handles_faults(engine):
    obs = {sid: f.observation for sid, f in engine.replay.fetch(engine.registry, __import__("datetime").date(2024, 5, 28)).items()}
    sample = dict(list(obs.items())[:8])
    rep = AWSNetwork(fault_rate=0.4, seed=3).sweep(sample)
    assert len(rep["events"]) == 24                       # 8 stations x 3 sensor threads
    assert rep["speedup"] > 1.5                            # threads overlapped
    assert sum(rep["counts"].values()) == 24
    assert rep["counts"].get("ok", 0) < 24                 # some faults were injected and caught


# ---------------------------------------------------------------- database
def test_database_is_read_only(engine, snap):
    with ClimateDatabase() as db:
        db.load_stations(engine.stations)
        db.load_readings(snap["stations"])
        assert db.table_counts() == {"stations": 50, "readings": 50}
        res = db.run_readonly("SELECT COUNT(*) FROM readings WHERE alert_level = 'RED'")
        assert res["rows"][0][0] == snap["summary"]["levels"]["RED"]
        for bad in ("DELETE FROM stations", "DROP TABLE readings", "SELECT 1; SELECT 2",
                    "UPDATE readings SET tmax = 0", "ATTACH DATABASE 'x.db' AS x"):
            with pytest.raises(QueryNotAllowedError):
                db.run_readonly(bad)


# ---------------------------------------------------------------- IMD grid files
def test_grd_roundtrip(tmp_path):
    grid = [[None if (r + c) % 7 == 0 else 20 + r * 0.5 for c in range(31)] for r in range(31)]
    path = tmp_path / "tmax.grd"
    IMDGridReader.write(path, [grid, grid])
    reader = IMDGridReader(path)
    assert reader.days == 2
    assert reader.value_at(7.5, 68.5, 1) == pytest.approx(20.0)
    assert reader.read_day(0)[0][0] is None
    with pytest.raises(GridFileError):
        reader.read_day(5)


# ---------------------------------------------------------------- web
@pytest.mark.parametrize("path,status", [
    ("/", 200), ("/?lead=3&field=watch&region=NW", 200), ("/station/WS119", 200), ("/warnings?level=RED", 200),
    ("/skill", 200), ("/climate", 200), ("/aws?n=5&fault=0.3", 200), ("/data?preset=3", 200), ("/about", 200),
    ("/station/NOPE", 404), ("/missing", 404), ("/api/snapshot", 200), ("/api/station?id=WS101", 200),
    ("/api/index?__path=skill", 200),
])
def test_routes(path, status):
    from tapmaan.web import route
    code, ctype, body, _ = route("GET", path)
    assert code == status, body[:300]
    assert body
