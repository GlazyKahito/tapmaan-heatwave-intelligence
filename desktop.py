"""Tapmaan Heatwave Operations Console - Tkinter desktop edition.

Runs fully on the desktop with the same Python core as the website:

    python desktop.py

Screens: Landing · Heatwave Watch (gridded map) · Station Outlook · Early Warnings ·
AWS Network (live threads) · Forecast Skill & Climate (Matplotlib / Seaborn).
Worker threads never touch Tkinter: they push results onto a queue.Queue that the GUI
drains with root.after(), because Tkinter is not thread-safe.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from tapmaan.aws_network import AWSNetwork  # noqa: E402
from tapmaan.config import ALERT_META  # noqa: E402
from tapmaan.engine import HeatwaveIntelligence  # noqa: E402
from tapmaan.logo import HEIGHT, WIDTH, draw_on  # noqa: E402
from tapmaan.stations_data import REGIONS  # noqa: E402
from tapmaan.webui.mapsvg import anom_colour, impact_colour, temp_colour  # noqa: E402

BG, PANEL, PANEL2, LINE = "#0a0f1c", "#121a2e", "#172038", "#222d48"
INK, MUTED, ACCENT = "#e9edf7", "#95a0bd", "#ff8c1a"
LEVEL = {k: v["colour"] for k, v in ALERT_META.items()}
FONT = ("Segoe UI", 10)
H1 = ("Segoe UI Semibold", 18)
H2 = ("Segoe UI Semibold", 12)
MONO = ("Consolas", 10)


def style_axes(fig, ax):
    fig.patch.set_facecolor(PANEL)
    ax.set_facecolor(PANEL)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_color(MUTED)
    ax.grid(color=LINE, linestyle=":", linewidth=.8)


class Screen(tk.Frame):
    """Base class for every screen; subclasses override build() and refresh()."""

    title = "Screen"

    def __init__(self, app):
        super().__init__(app.body, bg=BG)
        self.app = app
        tk.Label(self, text=self.title, bg=BG, fg=INK, font=H1, anchor="w").pack(fill="x", padx=18, pady=(14, 6))
        self.build()

    def build(self):
        pass

    def refresh(self):
        pass

    def panel(self, parent, title=None, **pack):
        frame = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        frame.pack(**pack)
        if title:
            tk.Label(frame, text=title, bg=PANEL, fg=INK, font=H2, anchor="w").pack(fill="x", padx=12, pady=(10, 4))
        return frame


class LandingScreen(Screen):
    title = ""

    def build(self):
        c = tk.Canvas(self, width=WIDTH, height=HEIGHT, bg=BG, highlightthickness=0)
        c.pack(pady=(40, 10))
        draw_on(c)
        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=MONO, justify="left")
        self.status.pack(pady=10)
        self.enter = tk.Button(self, text="ENTER OPERATIONS CONSOLE", command=lambda: self.app.show("watch"),
                               bg=ACCENT, fg="#160a00", font=("Segoe UI Semibold", 12), relief="flat", padx=24, pady=8,
                               state="disabled", cursor="hand2")
        self.enter.pack(pady=10)
        self.steps = ["Loading 50 stations across 7 IMD regions", "Reading 30-year ERA5 climatology",
                      "Training regional ridge forecaster", "Computing Getis-Ord hotspots", "Early warning engine ready"]
        self.done = 0
        self.after(350, self.tick)

    def tick(self):
        if self.done < len(self.steps):
            self.done += 1
            self.status.config(text="\n".join(f"✓ {s}" for s in self.steps[:self.done]))
            self.after(350, self.tick)
        else:
            self.enter.config(state="normal")


class WatchScreen(Screen):
    title = "Heatwave Watch"
    K = 17.0

    def build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=18)
        self.mode = tk.StringVar(value="replay")
        self.lead = tk.IntVar(value=0)
        self.field = tk.StringVar(value="tmax")
        for m in ("replay", "live", "simulated"):
            ttk.Radiobutton(bar, text=m.title(), value=m, variable=self.mode, command=self.app.reload).pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        eng = self.app.engine
        lo, hi = eng.replay.date_range
        self.dates = eng.replay.dates[eng.replay.dates.index(lo):eng.replay.dates.index(hi) + 1]
        self.date_idx = tk.IntVar(value=self.dates.index("2024-05-28"))
        self.scale = ttk.Scale(bar, from_=0, to=len(self.dates) - 1, variable=self.date_idx, length=260,
                               command=lambda _v: self.app.reload())
        self.scale.pack(side="left", padx=6)
        self.play_btn = ttk.Button(bar, text="▶ Play", command=self.toggle_play)
        self.play_btn.pack(side="left", padx=4)
        self.playing = False
        self.date_lbl = tk.Label(bar, text="", bg=BG, fg=INK, font=MONO)
        self.date_lbl.pack(side="left", padx=8)

        bar2 = tk.Frame(self, bg=BG)
        bar2.pack(fill="x", padx=18, pady=6)
        for i, lbl in enumerate(["Observed", "Day 1", "Day 2", "Day 3", "Day 4", "Day 5"]):
            ttk.Radiobutton(bar2, text=lbl, value=i, variable=self.lead, command=self.refresh).pack(side="left")
        ttk.Separator(bar2, orient="vertical").pack(side="left", fill="y", padx=8)
        for v, lbl in (("tmax", "Max temp"), ("anom", "Departure"), ("watch", "Heatwave watch")):
            ttk.Radiobutton(bar2, text=lbl, value=v, variable=self.field, command=self.refresh).pack(side="left")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=6)
        self.canvas = tk.Canvas(body, width=560, height=580, bg="#0b1324", highlightthickness=0)
        self.canvas.pack(side="left")
        side = tk.Frame(body, bg=BG)
        side.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.kpi = self.panel(side, "Alert levels", fill="x")
        self.kpi_lbl = tk.Label(self.kpi, bg=PANEL, fg=INK, font=("Consolas", 12), justify="left", anchor="w")
        self.kpi_lbl.pack(fill="x", padx=12, pady=(0, 10))
        hot = self.panel(side, "Hottest stations", fill="both", expand=True, pady=(10, 0))
        self.hot = tk.Listbox(hot, bg=PANEL, fg=INK, font=MONO, borderwidth=0, highlightthickness=0,
                              selectbackground=PANEL2, activestyle="none")
        self.hot.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.hot.bind("<Double-Button-1>", self.open_from_list)
        self.tip = tk.Label(side, text="Click a station on the map for its outlook.", bg=BG, fg=MUTED, font=FONT,
                            wraplength=320, justify="left")
        self.tip.pack(fill="x", pady=8)

    def toggle_play(self):
        self.playing = not self.playing
        self.play_btn.config(text="❚❚ Pause" if self.playing else "▶ Play")
        if self.playing:
            self.step()

    def step(self):
        if not self.playing:
            return
        i = self.date_idx.get()
        if i >= len(self.dates) - 1:
            self.toggle_play()
            return
        self.date_idx.set(i + 1)
        self.app.reload()
        self.after(700, self.step)

    def px(self, lat, lon):
        return 10 + (lon - 66.0) * self.K * 0.93, 10 + (38.5 - lat) * self.K

    def refresh(self):
        snap = self.app.snapshot
        if snap is None:
            return
        self.date_lbl.config(text=f"{snap['as_of']}  ·  {snap['source'].split(' - ')[0]}")
        lead, field = self.lead.get(), self.field.get()
        key = {"tmax": "tmax_", "anom": "anom_", "watch": "p_"}[field] + str(lead)
        colour = {"tmax": temp_colour, "anom": anom_colour, "watch": impact_colour}[field]
        c = self.canvas
        c.delete("all")
        w, h = self.K * 0.93 + 0.5, self.K + 0.5
        for (lat, lon), v in zip(self.app.engine.grid.cells, snap["grid"][key]):
            fill = colour(v)
            if fill:
                x, y = self.px(lat, lon)
                c.create_rectangle(x - w / 2, y - h / 2, x + w / 2, y + h / 2, fill=fill, outline="")
        for row in snap["stations"]:
            st = row["station"]
            x, y = self.px(st["lat"], st["lon"])
            if (row.get("hotspot_z") or 0) >= 1.96:
                c.create_oval(x - 9, y - 9, x + 9, y + 9, outline="white", dash=(2, 2))
            dot = c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=LEVEL[row["alert"]["level"]], outline="#0b1324", width=2)
            c.tag_bind(dot, "<Button-1>", lambda _e, sid=st["id"]: self.app.open_station(sid))
            c.tag_bind(dot, "<Enter>", lambda _e, r=row: self.tip.config(
                text=f"{r['station']['city']} · {r['alert']['level']} · Tmax {r['obs']['tmax']:.1f} °C "
                     f"({r['anomaly']:+.1f}) · {r['category']}"))
        lv = snap["summary"]["levels"]
        self.kpi_lbl.config(text=f"RED {lv['RED']:>3}   ORANGE {lv['ORANGE']:>3}\nYELLOW {lv['YELLOW']:>2}   GREEN {lv['GREEN']:>4}")
        self.hot.delete(0, "end")
        self.hot_ids = []
        for h in snap["summary"]["hottest"]:
            self.hot.insert("end", f"{h['city']:<16}{h['tmax']:>6.1f} °C")
            self.hot_ids.append(h["id"])

    def open_from_list(self, _event):
        sel = self.hot.curselection()
        if sel:
            self.app.open_station(self.hot_ids[sel[0]])


class StationScreen(Screen):
    title = "Station Outlook"

    def build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=18)
        names = [f"{s.station_id}  {s.city}" for s in self.app.engine.stations]
        self.pick = ttk.Combobox(top, values=names, width=30, state="readonly")
        self.pick.set(names[18])
        self.pick.pack(side="left")
        self.pick.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.head = tk.Label(top, text="", bg=BG, fg=INK, font=H2)
        self.head.pack(side="left", padx=14)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=8)
        self.fig = Figure(figsize=(6.4, 3.6), dpi=96)
        self.ax = self.fig.add_subplot(111)
        self.chart = FigureCanvasTkAgg(self.fig, master=body)
        self.chart.get_tk_widget().pack(side="left", fill="both", expand=True)
        self.text = tk.Text(body, bg=PANEL, fg=INK, font=("Consolas", 9), width=46, wrap="word", borderwidth=0, padx=10, pady=10)
        self.text.pack(side="left", fill="both", padx=(12, 0))

    def select(self, sid):
        for v in self.pick["values"]:
            if v.startswith(sid):
                self.pick.set(v)

    def refresh(self):
        sid = self.pick.get().split()[0]
        d = self.app.engine.station_detail(sid, self.app.mode, self.app.date)
        st, alert = d["station"], d["alert"]
        self.head.config(text=f"{st['city']}, {st['state']} — {alert['level']} · {d['category']}",
                         fg=LEVEL[alert["level"]])
        ax = self.ax
        ax.clear()
        style_axes(self.fig, ax)
        n = len(d["history"]["dates"])
        xs_h = list(range(n))
        xs_f = list(range(n - 1, n + 5))
        today = d["history"]["tmax"][-1]
        ax.plot(range(n + 5), d["history"]["normal"] + [f["normal"] for f in d["forecast"]], color=MUTED, ls="--", lw=1)
        ax.fill_between(xs_f, [today] + [f["lo"] for f in d["forecast"]], [today] + [f["hi"] for f in d["forecast"]],
                        color=ACCENT, alpha=.2, lw=0)
        ax.plot(xs_f, [today] + [f["tmax"] for f in d["forecast"]], color=ACCENT, lw=2, ls="--", marker="o", ms=3)
        ax.plot(xs_h, d["history"]["tmax"], color="#f4c430", lw=2.2, marker="o", ms=3)
        if d["future"]["tmax"]:
            ax.plot(range(n, n + len(d["future"]["tmax"])), d["future"]["tmax"], "D", color="#2fbf71", ms=5)
        ax.axhline(d["hw_threshold"], color="#e8352b", lw=1, alpha=.7)
        ax.axvline(n - 1, color=MUTED, lw=.8, ls=":")
        ax.set_ylabel("Tmax (°C)")
        self.fig.tight_layout()
        self.chart.draw()

        lines = [alert["explanation"], ""]
        lines += [f"{r['title']:<26}{r['score']:>5.0f} × {r['weight']:.2f}" for r in alert["rules"]]
        lines += ["", "FIVE-DAY OUTLOOK"]
        lines += [f"Day {f['lead']} {f['date']}  {f['tmax']:5.1f} °C  P(HW) {f['p_heatwave']:>4.0%}" for f in d["forecast"]]
        lines += ["", "ADVISORIES (draft until approved)"]
        for a in d["advisories"]:
            lines += [f"[{a['audience']}] {a['headline']}"] + [f"  • {x}" for x in a["actions"][:3]]
        lines += ["", "SMS"] + [m["text"] for m in d["messages"][:3]]
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(lines))


class WarningsScreen(Screen):
    title = "Early Warning Centre"

    def build(self):
        cols = ("city", "state", "region", "level", "score", "category", "tmax", "dep", "p72")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=24)
        for c, w, lbl in zip(cols, (150, 150, 70, 80, 60, 150, 70, 70, 80),
                             ("Station", "State", "Region", "Level", "Score", "Category", "Tmax", "Dep.", "P(HW 72h)")):
            self.tree.heading(c, text=lbl)
            self.tree.column(c, width=w, anchor="w")
        for lvl, colour in LEVEL.items():
            self.tree.tag_configure(lvl, foreground=colour)
        self.tree.pack(fill="both", expand=True, padx=18, pady=8)
        self.tree.bind("<Double-1>", self.open)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = sorted(self.app.snapshot["stations"], key=lambda r: r["alert"]["score"], reverse=True)
        for r in rows:
            st = r["station"]
            self.tree.insert("", "end", iid=st["id"], tags=(r["alert"]["level"],), values=(
                st["city"], st["state"], st["region"], r["alert"]["level"], f"{r['alert']['score']:.0f}",
                r["category"], f"{r['obs']['tmax']:.1f}", f"{r['anomaly']:+.1f}",
                f"{max(f['p_heatwave'] for f in r['forecast'][:3]):.0%}"))

    def open(self, _e):
        sel = self.tree.selection()
        if sel:
            self.app.open_station(sel[0])


class AWSScreen(Screen):
    title = "AWS Network Monitor"

    def build(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=18)
        tk.Label(bar, text="Fault rate", bg=BG, fg=MUTED, font=FONT).pack(side="left")
        self.fault = tk.DoubleVar(value=0.2)
        ttk.Scale(bar, from_=0, to=0.6, variable=self.fault, length=180).pack(side="left", padx=6)
        ttk.Button(bar, text="Run concurrent sweep", command=self.run).pack(side="left", padx=8)
        self.summary = tk.Label(bar, text="", bg=BG, fg=INK, font=MONO)
        self.summary.pack(side="left", padx=10)
        self.log = tk.Text(self, bg=PANEL, fg=INK, font=MONO, borderwidth=0, padx=10, pady=10)
        self.log.pack(fill="both", expand=True, padx=18, pady=8)
        for tag, colour in (("ok", "#8fe9b6"), ("invalid", "#ffb36b"), ("missing", "#ffd75e"), ("comm_failure", "#ff8f88")):
            self.log.tag_configure(tag, foreground=colour)
        self.q = queue.Queue()

    def run(self):
        self.log.delete("1.0", "end")
        obs = {sid: f.observation for sid, f in self.app.feeds.items()}
        net = AWSNetwork(fault_rate=round(self.fault.get(), 2))
        threading.Thread(target=lambda: self.q.put(net.sweep(obs)), daemon=True).start()
        self.after(50, self.poll)

    def poll(self):
        try:
            rep = self.q.get_nowait()
        except queue.Empty:
            self.after(50, self.poll)
            return
        city = {s.station_id: s.city for s in self.app.engine.stations}
        for ev in rep["events"]:
            shown = ev["value"] if ev["status"] == "ok" else ev["message"]
            self.log.insert("end", f"{ev['start_ms']:>8.1f} ms  {ev['thread']:<12}{city[ev['station_id']]:<20}"
                                   f"{ev['status'].upper():<14}{shown}\n", ev["status"])
        self.summary.config(text=f"wall {rep['wall_ms']:.0f} ms · sum {rep['sequential_ms']:.0f} ms · "
                                 f"{rep['speedup']}× · {rep['counts']}")


class AnalyticsScreen(Screen):
    title = "Forecast Skill & Climate"

    def build(self):
        self.fig = Figure(figsize=(11, 4.6), dpi=96)
        self.chart = FigureCanvasTkAgg(self.fig, master=self)
        self.chart.get_tk_widget().pack(fill="both", expand=True, padx=18, pady=8)
        self.drawn = False

    def refresh(self):
        if self.drawn:
            return
        import seaborn as sns
        import pandas as pd
        val = self.app.engine.validation()
        rep = self.app.engine.climate_analysis()
        ax1, ax2 = self.fig.add_subplot(121), self.fig.add_subplot(122)
        for ax in (ax1, ax2):
            style_axes(self.fig, ax)
        leads = [r["lead"] for r in val["leads"]]
        w = .27
        for k, (key, colour) in enumerate((("model", ACCENT), ("persistence", "#5b6b95"), ("climatology", "#2c3a5c"))):
            ax1.bar([x + (k - 1) * w for x in leads], [r[key]["mae"] for r in val["leads"]], w, color=colour, label=key)
        ax1.set_title("Forecast error 2024 (MAE °C)", color=INK, fontsize=10)
        ax1.legend(facecolor=PANEL, labelcolor=MUTED, edgecolor=LINE, fontsize=8)
        df = pd.DataFrame(rep["season_table"]).set_index("name").drop(columns="region")
        sns.heatmap(df, annot=True, fmt=".1f", cmap="YlOrRd", ax=ax2, cbar=False, annot_kws={"fontsize": 8})
        ax2.set_title("Region × season mean Tmax", color=INK, fontsize=10)
        ax2.set_ylabel("")
        self.fig.tight_layout()
        self.chart.draw()
        self.drawn = True


class OperationsConsole(tk.Tk):
    SCREENS = {"landing": LandingScreen, "watch": WatchScreen, "station": StationScreen,
               "warnings": WarningsScreen, "aws": AWSScreen, "analytics": AnalyticsScreen}
    NAV = [("watch", "Heatwave Watch"), ("station", "Station Outlook"), ("warnings", "Early Warnings"),
           ("aws", "AWS Network"), ("analytics", "Skill & Climate")]

    def __init__(self):
        super().__init__()
        self.title("Tapmaan · Heatwave Operations Console")
        self.geometry("1280x800")
        self.configure(bg=BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=INK, fieldbackground=PANEL)
        style.configure("TRadiobutton", background=BG, foreground=MUTED)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK, rowheight=24)
        style.configure("Treeview.Heading", background=PANEL2, foreground=MUTED)

        self.engine = HeatwaveIntelligence.shared()
        self.mode, self.date, self.snapshot, self.feeds = "replay", "2024-05-28", None, {}
        self.results = queue.Queue()

        nav = tk.Frame(self, bg=PANEL, width=200)
        nav.pack(side="left", fill="y")
        tk.Label(nav, text="TAPMAAN", bg=PANEL, fg=ACCENT, font=("Segoe UI Black", 16)).pack(pady=(18, 0))
        tk.Label(nav, text="Heatwave Operations", bg=PANEL, fg=MUTED, font=FONT).pack(pady=(0, 18))
        for key, label in self.NAV:
            tk.Button(nav, text=label, command=lambda k=key: self.show(k), bg=PANEL, fg=INK, relief="flat",
                      activebackground=PANEL2, activeforeground=INK, anchor="w", padx=18, pady=8,
                      font=FONT, cursor="hand2").pack(fill="x")
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(side="left", fill="both", expand=True)
        self.screens = {k: cls(self) for k, cls in self.SCREENS.items()}
        self.current = None
        self.show("landing")
        self.reload()
        self.after(60, self.drain)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def show(self, key):
        if self.current:
            self.current.pack_forget()
        self.current = self.screens[key]
        self.current.pack(fill="both", expand=True)
        if self.snapshot is not None:
            self.current.refresh()

    def reload(self):
        """Fetch a new snapshot on a worker thread (live mode needs the network)."""
        watch = self.screens.get("watch") if hasattr(self, "screens") else None
        if watch is not None:
            self.mode = watch.mode.get()
            self.date = watch.dates[int(float(watch.date_idx.get()))]

        def work(mode=self.mode, date=self.date):
            snap = self.engine.snapshot(mode, date)
            _, provider, as_of = self.engine.resolve(mode, date)
            self.results.put((snap, provider.fetch(self.engine.registry, as_of)))
        threading.Thread(target=work, daemon=True).start()

    def drain(self):
        try:
            while True:
                self.snapshot, self.feeds = self.results.get_nowait()
                if self.current is not None:
                    self.current.refresh()
        except queue.Empty:
            pass
        self.after(60, self.drain)

    def open_station(self, sid):
        self.screens["station"].select(sid)
        self.show("station")


if __name__ == "__main__":
    OperationsConsole().mainloop()
