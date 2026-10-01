"""SQLite repository for stations and readings + a safe, read-only Data Explorer.

Two tables, 50 rows each:
    stations(station_id PK, city, state, latitude, longitude, region, terrain)
    readings(reading_id PK AUTOINCREMENT, station_id FK, obs_date, tmax, tmin, humidity,
             wind_speed, heat_index, anomaly, category, alert_level)

The Data Explorer runs user queries through sqlite3's authorizer so only SELECT statements that
read data are allowed, with a row limit and an instruction budget.
"""

import sqlite3

from .config import SQL_MAX_ROWS
from .exceptions import QueryNotAllowedError

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    city       TEXT NOT NULL,
    state      TEXT NOT NULL,
    latitude   REAL,
    longitude  REAL,
    region     TEXT,
    terrain    TEXT
);
CREATE TABLE IF NOT EXISTS readings (
    reading_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id  TEXT NOT NULL REFERENCES stations(station_id),
    obs_date    TEXT NOT NULL,
    tmax        REAL,
    tmin        REAL,
    humidity    REAL,
    wind_speed  REAL,
    heat_index  REAL,
    anomaly     REAL,
    category    TEXT,
    alert_level TEXT
);
"""

PRESET_QUERIES = [
    ("All stations", "SELECT * FROM stations;"),
    ("Only city, state, region", "SELECT city, state, region FROM stations;"),
    ("Stations in the North West region", "SELECT * FROM stations WHERE region = 'NW';"),
    ("Readings hotter than 45 °C", "SELECT * FROM readings WHERE tmax > 45 ORDER BY tmax DESC;"),
    ("Hot AND humid (tmax >= 35 AND humidity >= 60)",
     "SELECT station_id, tmax, humidity, heat_index FROM readings WHERE tmax >= 35 AND humidity >= 60;"),
    ("RED or ORANGE alerts (OR)",
     "SELECT station_id, tmax, alert_level FROM readings WHERE alert_level = 'RED' OR alert_level = 'ORANGE';"),
    ("Terrain IN (coastal, hilly)", "SELECT city, terrain FROM stations WHERE terrain IN ('coastal', 'hilly');"),
    ("Tmax BETWEEN 40 AND 45", "SELECT station_id, tmax FROM readings WHERE tmax BETWEEN 40 AND 45;"),
    ("Cities starting with 'B' (LIKE)", "SELECT city, state FROM stations WHERE city LIKE 'B%';"),
    ("Distinct alert levels", "SELECT DISTINCT alert_level FROM readings;"),
    ("Top 10 hottest (ORDER BY ... LIMIT)",
     "SELECT s.city, r.tmax FROM readings r JOIN stations s USING (station_id) ORDER BY r.tmax DESC LIMIT 10;"),
    ("Average Tmax per region (GROUP BY + JOIN)",
     "SELECT s.region, ROUND(AVG(r.tmax), 1) AS avg_tmax, COUNT(*) AS stations, MAX(r.tmax) AS max_tmax\n"
     "FROM readings r JOIN stations s ON s.station_id = r.station_id\nGROUP BY s.region ORDER BY avg_tmax DESC;"),
    ("States with 2+ heatwave stations (HAVING)",
     "SELECT s.state, COUNT(*) AS heatwave_stations FROM readings r JOIN stations s USING (station_id)\n"
     "WHERE r.category <> 'NORMAL' GROUP BY s.state HAVING COUNT(*) >= 2 ORDER BY heatwave_stations DESC;"),
    ("Largest anomalies", "SELECT station_id, tmax, anomaly FROM readings ORDER BY anomaly DESC LIMIT 10;"),
]

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
if hasattr(sqlite3, "SQLITE_RECURSIVE"):
    _ALLOWED_ACTIONS.add(sqlite3.SQLITE_RECURSIVE)


class ClimateDatabase:
    """Context-managed SQLite database (in memory by default)."""

    def __init__(self, path=":memory:"):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        self.conn.close()

    # ---- writes ----------------------------------------------------------------
    def load_stations(self, stations):
        rows = [(s.station_id, s.city, s.state, s.latitude, s.longitude, s.region, s.terrain) for s in stations]
        with self.conn:  # transaction
            self.conn.executemany("INSERT OR REPLACE INTO stations VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)

    def load_readings(self, rows):
        """rows: snapshot station dicts from the engine."""
        data = [(r["station"]["id"], r["obs"]["date"], r["obs"]["tmax"], r["obs"]["tmin"], r["obs"]["humidity"],
                 r["obs"]["wind"], r["heat_index"], r["anomaly"], r["category"], r["alert"]["level"])
                for r in rows]
        with self.conn:
            self.conn.executemany(
                "INSERT INTO readings (station_id, obs_date, tmax, tmin, humidity, wind_speed, heat_index,"
                " anomaly, category, alert_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        return len(data)

    # ---- reads -----------------------------------------------------------------
    def table_counts(self):
        cur = self.conn.cursor()
        return {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("stations", "readings")}

    def run_readonly(self, sql, max_rows=SQL_MAX_ROWS):
        sql = (sql or "").strip()
        if not sql:
            raise QueryNotAllowedError("Empty query")
        if len(sql) > 2000:
            raise QueryNotAllowedError("Query is too long (2000 characters max)")
        if sql.rstrip(";").count(";"):
            raise QueryNotAllowedError("Only one statement at a time")

        def authorizer(action, *_args):
            return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY

        budget = {"ticks": 0}

        def progress():
            budget["ticks"] += 1
            return 1 if budget["ticks"] > 2000 else 0  # non-zero aborts the query

        self.conn.set_authorizer(authorizer)
        self.conn.set_progress_handler(progress, 1000)
        try:
            cur = self.conn.execute(sql)
            columns = [d[0] for d in cur.description or []]
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.DatabaseError as err:
            msg = str(err)
            if "not authorized" in msg:
                msg = "Only read-only SELECT queries are allowed in the Data Explorer"
            elif "interrupted" in msg:
                msg = "Query took too long and was stopped"
            raise QueryNotAllowedError(msg) from err
        finally:
            self.conn.set_authorizer(None)
            self.conn.set_progress_handler(None, 0)
        return {"columns": columns, "rows": [list(r) for r in rows[:max_rows]],
                "truncated": len(rows) > max_rows}
