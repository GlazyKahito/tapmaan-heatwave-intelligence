"""Matplotlib + Seaborn charts rendered to inline SVG for the website.

Pandas shapes the data, NumPy does the numeric work (trend fits, rolling means) and
Matplotlib/Seaborn draw. Text stays as real SVG text so it inherits the page fonts.
"""

import io
import os
import re
from datetime import date

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

# vintage almanac palette (matches public/css/app.css)
INK, MUTED, GRID, PANEL = "#eadfc6", "#9d8d71", "#3a2f25", "#16110d"
ORANGE, RED, YELLOW, GREEN, BLUE, VIOLET = "#d9822b", "#cf5240", "#d4a93f", "#8fa86f", "#7d9cbb", "#a98bb0"
OCHRE, SEPIA, TAN = "#c9a24a", "#6f624f", "#7d6b52"
REGION_COLOURS = {"WH": "#7d9cbb", "NW": "#cf5240", "NC": "#d9822b", "NE": "#8fa86f",
                  "WC": "#6fb0a8", "EC": "#a98bb0", "IP": "#d4a93f"}
STATUS_COLOURS = {"ok": GREEN, "invalid": ORANGE, "missing": OCHRE, "comm_failure": RED, "error": VIOLET}

plt.rcParams.update({
    "svg.fonttype": "none", "font.family": "serif",
    "font.serif": ["Source Serif 4", "Georgia", "DejaVu Serif"], "font.size": 10.5,
    "text.color": INK, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": SEPIA, "axes.linewidth": 0.9, "axes.facecolor": "none", "figure.facecolor": "none",
    "axes.grid": True, "grid.color": GRID, "grid.linestyle": (0, (1, 3)), "grid.linewidth": 0.9,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "legend.labelcolor": MUTED, "axes.titlecolor": INK, "axes.titlesize": 11,
})


def svg(fig, css="mpl"):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", transparent=True, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    text = buf.getvalue()
    text = text[text.index("<svg"):]
    text = re.sub(r'<svg([^>]*?)\swidth="[^"]+"\s+height="[^"]+"', rf'<svg\1 class="{css}"', text, count=1)
    return re.sub(r"<metadata>.*?</metadata>", "", text, flags=re.S)


def _short(iso):
    return date.fromisoformat(iso).strftime("%d %b")


# ---------------------------------------------------------------- station forecast
def forecast_chart(detail):
    hist = detail["history"]
    fc = detail["forecast"]
    hd = [_short(d) for d in hist["dates"]]
    fd = [_short(d["date"]) for d in fc]
    x_hist = np.arange(len(hd))
    x_fc = np.arange(len(hd) - 1, len(hd) + len(fd))

    fig, ax = plt.subplots(figsize=(10.5, 4.3))
    ax.plot(np.arange(len(hd) + len(fd)), hist["normal"] + [d["normal"] for d in fc],
            color=MUTED, ls=(0, (4, 3)), lw=1.3, label="Normal (1995–2024)")
    thr = [detail["hw_threshold"]] * len(hd) + [d["heatwave_threshold"] for d in fc]
    ax.step(np.arange(len(thr)), thr, where="mid", color=RED, lw=1.1, alpha=.75, label="Heatwave threshold")

    today = hist["tmax"][-1]
    lo = [today] + [d["lo"] for d in fc]
    hi = [today] + [d["hi"] for d in fc]
    mean = [today] + [d["tmax"] for d in fc]
    ax.fill_between(x_fc, lo, hi, color=OCHRE, alpha=.28, lw=0, label="80% forecast interval")
    ax.plot(x_fc, mean, color=ORANGE, lw=2.2, ls=(0, (5, 2)), marker="o", ms=4, label="AI forecast")
    ax.plot(x_hist, hist["tmax"], color=INK, lw=2.2, marker="o", ms=3.6, label="Observed Tmax")

    fut = detail["future"]
    if fut["tmax"]:
        xs = np.arange(len(hd), len(hd) + len(fut["tmax"]))
        if fut["kind"] == "observed":
            ax.plot(xs, fut["tmax"], color=GREEN, lw=0, marker="D", ms=6, mec=PANEL, label="What actually happened")
        else:
            ax.plot(xs, fut["tmax"], color=VIOLET, lw=1.6, marker="s", ms=4, label="Reference model (Open-Meteo)")

    ax.axvline(len(hd) - 1, color=MUTED, lw=1, ls=":")
    ax.text(len(hd) - 0.9, ax.get_ylim()[1], " today", va="top", color=MUTED, fontsize=9)
    labels = hd + fd
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=0, fontsize=8.5)
    for i, t in enumerate(ax.get_xticklabels()):
        t.set_visible(i % 2 == (len(labels) - 1) % 2)
    ax.set_ylabel("Max temperature (°C)")
    ax.legend(ncol=3, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, -0.12))
    return svg(fig)


def seasonal_cycle_chart(monthly_means, normal_today_month):
    """Station climatology: mean monthly Tmax with the 30-year spread."""
    df = pd.DataFrame(monthly_means).T.apply(pd.to_numeric)  # rows = years, cols = months 0..11
    if df.empty:
        return ""
    df.columns = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    stats = df.agg(["mean", "min", "max"]).T
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    colours = [ORANGE if i == normal_today_month else TAN for i in range(12)]
    ax.bar(stats.index, stats["mean"], color=colours, width=.66)
    ax.vlines(stats.index, stats["min"], stats["max"], color=INK, lw=1.2, alpha=.6)
    ax.set_ylim(max(0, stats["min"].min() - 4), stats["max"].max() + 2)
    ax.set_ylabel("Mean Tmax (°C)")
    ax.tick_params(axis="x", labelsize=8)
    return svg(fig)


# ---------------------------------------------------------------- forecast skill
def skill_mae_chart(val):
    df = pd.DataFrame([{"Lead": f"Day {r['lead']}", "AI model": r["model"]["mae"],
                        "Persistence": r["persistence"]["mae"], "Climatology": r["climatology"]["mae"]}
                       for r in val["leads"]]).set_index("Lead")
    fig, ax = plt.subplots(figsize=(6.4, 3.3))
    df.plot.bar(ax=ax, color=[ORANGE, TAN, "#4a3d2e"], width=.78, rot=0)
    for c in ax.containers[:1]:
        ax.bar_label(c, fmt="%.2f", fontsize=8, color=INK, padding=2)
    ax.set_ylabel("Mean absolute error (°C)")
    ax.set_xlabel("")
    ax.legend(fontsize=8.5, loc="upper left")
    return svg(fig)


def skill_events_chart(val):
    df = pd.DataFrame([{"lead": r["lead"], "POD": r["events"]["pod"], "FAR": r["events"]["far"],
                        "CSI": r["events"]["csi"]} for r in val["leads"]]).set_index("lead")
    fig, ax = plt.subplots(figsize=(6.0, 3.3))
    for col, colour in (("POD", GREEN), ("CSI", ORANGE), ("FAR", RED)):
        ax.plot(df.index, df[col], marker="o", lw=2.2, color=colour, label=col)
    ax.set_ylim(0, 1)
    ax.set_xticks(df.index)
    ax.set_xticklabels([f"Day {i}" for i in df.index])
    ax.set_ylabel("Score (0–1)")
    ax.legend(fontsize=8.5, ncol=3, loc="upper right")
    return svg(fig)


def region_mae_chart(val, regions):
    s = pd.Series(val["region_mae_lead1"]).sort_values()
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    ax.barh([regions.get(k, k) for k in s.index], s.values, color=[REGION_COLOURS.get(k, ORANGE) for k in s.index])
    for y, v in enumerate(s.values):
        ax.text(v + 0.03, y, f"{v:.2f}", va="center", fontsize=8.5, color=INK)
    ax.set_xlabel("Day-1 MAE (°C)")
    ax.grid(axis="y", visible=False)
    return svg(fig)


# ---------------------------------------------------------------- climate trends
def season_heatmap(report):
    df = pd.DataFrame(report["season_table"]).set_index("name").drop(columns="region")
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    vintage = matplotlib.colors.LinearSegmentedColormap.from_list(
        "almanac", ["#34597c", "#6f8f86", "#c9a24a", "#d9822b", "#a33a2c"])
    sns.heatmap(df, annot=True, fmt=".1f", cmap=vintage, linewidths=2, linecolor=PANEL,
                cbar_kws={"label": "Mean Tmax (°C)", "shrink": .8}, ax=ax, annot_kws={"fontsize": 9})
    ax.grid(False)
    ax.set_ylabel("")
    ax.set_xlabel("")
    ax.tick_params(axis="both", length=0)
    ax.figure.axes[-1].yaxis.label.set_color(MUTED)
    ax.figure.axes[-1].tick_params(colors=MUTED)
    return svg(fig)


def trend_chart(report):
    fig, ax = plt.subplots(figsize=(13, 4.2))
    for s in report["series"]:
        series = pd.Series(s["mam_tmax"], index=s["years"], dtype=float)
        smooth = series.rolling(5, center=True, min_periods=3).mean()
        c = REGION_COLOURS.get(s["region"], ORANGE)
        ax.plot(series.index, series.values, color=c, lw=.8, alpha=.35)
        ax.plot(smooth.index, smooth.values, color=c, lw=2.2, label=s["name"])
    ax.set_ylabel("Pre-monsoon (Mar–May) mean Tmax (°C)")
    ax.legend(ncol=4, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, -0.1))
    return svg(fig)


def heatwave_days_chart(report):
    frames = [pd.Series(s["heatwave_days"], index=s["years"], name=s["region"]) for s in report["series"]]
    df = pd.concat(frames, axis=1)
    national = df.mean(axis=1)
    fig, ax = plt.subplots(figsize=(13, 3.6))
    ax.bar(national.index, national.values, color=[RED if v >= national.quantile(.8) else OCHRE
                                                   for v in national.values], width=.75)
    slope, intercept = np.polyfit(national.index.values.astype(float), national.values, 1)
    ax.plot(national.index, slope * national.index.values + intercept, color=INK, lw=1.4, ls="--",
            label=f"Trend {slope * 10:+.1f} days / decade")
    ax.set_ylabel("Heatwave days per station")
    ax.legend(fontsize=8.5, loc="upper left")
    return svg(fig)


# ---------------------------------------------------------------- AWS threads
def aws_gantt(report):
    lanes = ["temperature", "humidity", "wind"]
    fig, ax = plt.subplots(figsize=(13, 2.9))
    for i, lane in enumerate(lanes):
        for ev in (x for x in report["events"] if x["thread"] == lane):
            ax.broken_barh([(ev["start_ms"], max(ev["end_ms"] - ev["start_ms"], 0.4))], (i - 0.34, 0.68),
                           facecolors=STATUS_COLOURS.get(ev["status"], VIOLET), edgecolor=PANEL, lw=.6)
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels([f"{lane} thread" for lane in lanes])
    ax.invert_yaxis()
    ax.set_xlabel("Time since sweep start (ms)")
    ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in STATUS_COLOURS.values()]
    ax.legend(handles, ["ok", "invalid value", "missing", "comm failure", "other"], ncol=5, fontsize=8.5,
              loc="upper left", bbox_to_anchor=(0, -0.28))
    return svg(fig)
