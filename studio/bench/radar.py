"""Radar chart as pure SVG (no JS/CDN needed for share pages)."""

import math


def radar_svg(dim_scores, size=320):
    """dim_scores: list of (name_zh, score_or_None) in fixed order."""
    cx = cy = size / 2
    R = size / 2 - 56
    n = max(3, len(dim_scores))
    colors = {"pass": "#16a34a", "warn": "#d97706", "fail": "#dc2626", "info": "#6b7280"}
    lights = []

    def pt(i, frac):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang)

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img">' % (size, size, size, size)]
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join("%.1f,%.1f" % pt(i, ring) for i in range(n))
        parts.append('<polygon points="%s" fill="none" stroke="#e5e7eb" stroke-width="1"/>'
                     % pts if ring < 1.0 else
                     '<polygon points="%s" fill="none" stroke="#cbd5e1" stroke-width="1.5"/>' % pts)
    for i in range(n):
        x, y = pt(i, 1.0)
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#e5e7eb"/>' % (cx, cy, x, y))

    poly = []
    for i, (name, score, light) in enumerate(dim_scores):
        frac = max(0.03, min(1.0, (score or 0) / 100.0))
        poly.append(pt(i, frac))
        lights.append(light)
    px = " ".join("%.1f,%.1f" % p for p in poly)
    color = "#dc2626" if "fail" in lights else "#d97706" if "warn" in lights else "#2563eb"
    parts.append('<polygon points="%s" fill="%s" fill-opacity="0.25" stroke="%s" stroke-width="2"/>' % (px, color, color))
    for (x, y) in poly:
        parts.append('<circle cx="%.1f" cy="%.1f" r="3.5" fill="%s"/>' % (x, y, color))

    for i, (name, score, light) in enumerate(dim_scores):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        lx = cx + (R + 26) * math.cos(ang)
        ly = cy + (R + 26) * math.sin(ang)
        anchor = "middle"
        if math.cos(ang) > 0.3:
            anchor = "start"
        elif math.cos(ang) < -0.3:
            anchor = "end"
        c = colors.get(light, "#374151")
        label = name if score is None else "%s %d" % (name, score)
        parts.append('<text x="%.1f" y="%.1f" text-anchor="%s" font-size="13" fill="%s" font-family="system-ui,sans-serif">%s</text>'
                     % (lx, ly + 4, anchor, c, label))
    parts.append("</svg>")
    return "".join(parts)
