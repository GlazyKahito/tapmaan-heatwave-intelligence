"""The Tapmaan logo as a list of Tkinter Canvas drawing commands.

One source of truth, two renderers:
* draw_on(canvas) replays the commands on a real tkinter.Canvas (desktop console)
* to_svg() converts the same commands to SVG for the website
"""

import math

WIDTH, HEIGHT = 520, 240


def logo_commands():
    cx, cy = 120, 110
    cmds = [("create_rectangle", (0, 0, WIDTH, HEIGHT), {"fill": "#0b1020", "outline": ""})]

    # sun rays: 12 triangles (create_polygon)
    for k in range(12):
        a = math.radians(k * 30)
        a1, a2 = a - math.radians(7), a + math.radians(7)
        pts = (cx + 62 * math.cos(a1), cy + 62 * math.sin(a1),
               cx + 92 * math.cos(a), cy + 92 * math.sin(a),
               cx + 62 * math.cos(a2), cy + 62 * math.sin(a2))
        cmds.append(("create_polygon", tuple(round(p, 1) for p in pts), {"fill": "#ff8c1a", "outline": ""}))

    cmds += [
        ("create_oval", (cx - 60, cy - 60, cx + 60, cy + 60), {"fill": "#ff8c1a", "outline": ""}),
        ("create_oval", (cx - 46, cy - 46, cx + 46, cy + 46), {"fill": "#ffc845", "outline": ""}),
        # warning gauge around the sun (create_arc)
        ("create_arc", (cx - 104, cy - 104, cx + 104, cy + 104),
         {"start": 40, "extent": 100, "style": "arc", "outline": "#e8352b", "width": 5}),
        # thermometer: tube, mercury, bulb
        ("create_rectangle", (cx - 9, cy - 44, cx + 9, cy + 30), {"fill": "#fff7e6", "outline": "#0b1020", "width": 2}),
        ("create_rectangle", (cx - 4, cy - 20, cx + 4, cy + 32), {"fill": "#e8352b", "outline": ""}),
        ("create_oval", (cx - 18, cy + 22, cx + 18, cy + 58), {"fill": "#e8352b", "outline": "#0b1020", "width": 2}),
    ]
    # tick marks on the tube (create_line)
    for i in range(4):
        y = cy - 34 + i * 14
        cmds.append(("create_line", (cx + 9, y, cx + 16, y), {"fill": "#fff7e6", "width": 2}))

    # three heat-shimmer waves (smooth create_line)
    for row, colour in enumerate(("#ffc845", "#ff8c1a", "#e8352b")):
        y = 196 + row * 13
        pts = []
        for i in range(9):
            pts += [40 + i * 20, y + (6 if i % 2 else -6)]
        cmds.append(("create_line", tuple(pts), {"fill": colour, "width": 4, "smooth": True}))

    cmds += [
        ("create_text", (368, 88), {"text": "TAPMAAN", "fill": "#ffffff", "font": ("Helvetica", 34, "bold")}),
        ("create_text", (360, 128), {"text": "Heatwave Intelligence Grid", "fill": "#ffb347",
                                     "font": ("Helvetica", 15, "normal")}),
        ("create_line", (260, 150, 460, 150), {"fill": "#2a3450", "width": 2}),
        ("create_text", (360, 172), {"text": "KJS-CES-01  ·  Monitor · Predict · Warn", "fill": "#9aa4c0",
                                     "font": ("Helvetica", 11, "normal")}),
    ]
    return cmds


def draw_on(canvas, scale=1.0, vintage=False):
    """Replay the commands on a real tkinter.Canvas."""
    for method, coords, options in logo_commands():
        if vintage and method == "create_rectangle" and options.get("fill") == "#0b1020":
            continue
        opts = _recolour(options, VINTAGE) if vintage else dict(options)
        if "font" in opts:
            family, size, weight = opts["font"]
            opts["font"] = (family, int(size * scale), weight)
        getattr(canvas, method)(*[c * scale for c in coords], **opts)


def _svg_attrs(opts, shape=True):
    fill = opts.get("fill", "" if shape else "#000")
    outline = opts.get("outline", "#000" if shape else "")
    width = opts.get("width", 1)
    attrs = f'fill="{fill or "none"}"'
    if outline:
        attrs += f' stroke="{outline}" stroke-width="{width}"'
    return attrs


# Dark-vintage palette used by the website and the desktop console.
VINTAGE = {"#0b1020": None, "#ff8c1a": "#d9822b", "#ffc845": "#c9a24a", "#e8352b": "#cf5240",
           "#fff7e6": "#eadfc6", "#ffffff": "#eadfc6", "#ffb347": "#c9a24a", "#2a3450": "#54452f",
           "#9aa4c0": "#9d8d71"}


def _recolour(options, palette):
    out = dict(options)
    for key in ("fill", "outline"):
        if out.get(key) in palette:
            out[key] = palette[out[key]] or ""
    return out


def to_svg(scale=1.0, css_class="logo", vintage=True):
    """Translate the Tkinter canvas commands into an SVG document string."""
    parts, rays = [], []
    for method, c, o in logo_commands():
        if vintage:
            if method == "create_rectangle" and o.get("fill") == "#0b1020":
                continue  # transparent background on paper
            o = _recolour(o, VINTAGE)
        if method == "create_rectangle":
            x0, y0, x1, y1 = c
            parts.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" {_svg_attrs(o)}/>')
        elif method == "create_oval":
            x0, y0, x1, y1 = c
            parts.append(f'<ellipse cx="{(x0 + x1) / 2}" cy="{(y0 + y1) / 2}" rx="{(x1 - x0) / 2}" '
                         f'ry="{(y1 - y0) / 2}" {_svg_attrs(o)}/>')
        elif method == "create_polygon":
            pts = " ".join(f"{c[i]},{c[i + 1]}" for i in range(0, len(c), 2))
            rays.append(f'<polygon points="{pts}" {_svg_attrs(o)}/>')
        elif method == "create_line":
            pts = [(c[i], c[i + 1]) for i in range(0, len(c), 2)]
            if o.get("smooth") and len(pts) > 2:
                # Tk draws smooth lines as quadratic splines through the segment midpoints
                d = f"M{pts[0][0]},{pts[0][1]}"
                for i in range(1, len(pts) - 1):
                    mx, my = (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2
                    end = pts[-1] if i == len(pts) - 2 else (mx, my)
                    d += f" Q{pts[i][0]},{pts[i][1]} {end[0]},{end[1]}"
            else:
                d = "M" + " L".join(f"{x},{y}" for x, y in pts)
            parts.append(f'<path d="{d}" fill="none" stroke="{o.get("fill", "#000")}" '
                         f'stroke-width="{o.get("width", 1)}" stroke-linecap="round"/>')
        elif method == "create_arc":
            x0, y0, x1, y1 = c
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            a0 = math.radians(o.get("start", 0))
            a1 = math.radians(o.get("start", 0) + o.get("extent", 90))
            p0 = (cx + rx * math.cos(a0), cy - ry * math.sin(a0))
            p1 = (cx + rx * math.cos(a1), cy - ry * math.sin(a1))
            large = 1 if abs(o.get("extent", 90)) > 180 else 0
            d = f"M{p0[0]:.1f},{p0[1]:.1f} A{rx},{ry} 0 {large} 0 {p1[0]:.1f},{p1[1]:.1f}"
            parts.append(f'<path d="{d}" fill="none" stroke="{o.get("outline", "#000")}" '
                         f'stroke-width="{o.get("width", 1)}" stroke-linecap="round"/>')
        elif method == "create_text":
            family, size, weight = o.get("font", ("Helvetica", 12, "normal"))
            parts.append(f'<text x="{c[0]}" y="{c[1]}" fill="{o.get("fill", "#000")}" text-anchor="middle" '
                         f'dominant-baseline="central" font-family="Libre Caslon Text, Georgia, serif" '
                         f'font-size="{size * 1.333:.1f}" font-weight="{"700" if weight == "bold" else "400"}">'
                         f'{o.get("text", "")}</text>')
    parts.insert(0, f'<g class="ray">{"".join(rays)}</g>')
    w, h = WIDTH * scale, HEIGHT * scale
    return (f'<svg class="{css_class}" viewBox="0 0 {WIDTH} {HEIGHT}" width="{w:.0f}" height="{h:.0f}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Tapmaan logo">{"".join(parts)}</svg>')
