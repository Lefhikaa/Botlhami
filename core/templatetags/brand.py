"""Brand artwork drawn in code, so it stays sharp and can be animated with CSS."""
from functools import lru_cache
from math import hypot, sqrt

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

UMBER, EMBER, SORGHUM, CRIMSON, WHITE = "#5c2a22", "#f26725", "#faa61c", "#9f2421", "#ffffff"


@lru_cache(maxsize=4)
def _medallion(rings=5, side=34):
    """A hexagonal woven medallion made of triangles, after Botswana basketry.

    It is built from the centre outwards: one sorghum triangle (the idea) grows ring by
    ring into the full weave (the solution). Each triangle carries its ring number so CSS
    can stagger the build.
    """
    h = side * sqrt(3) / 2
    size = 2 * rings * side + 8
    c = size / 2
    tris = []
    rows = 2 * rings
    for r in range(-rings, rings):
        y0 = r * h
        for k in range(-2 * rings, 2 * rings + 1):
            x0 = k * side / 2
            up = (k + r) % 2 == 0
            if up:
                pts = [(x0, y0 + h), (x0 + side / 2, y0), (x0 + side, y0 + h)]
            else:
                pts = [(x0, y0), (x0 + side, y0), (x0 + side / 2, y0 + h)]
            cx = sum(p[0] for p in pts) / 3 - side / 2
            cy = sum(p[1] for p in pts) / 3
            pts = [(px - side / 2, py) for px, py in pts]
            # keep triangles inside the hexagon
            if abs(cy) > rings * h or abs(cx) * sqrt(3) + abs(cy) > rings * 2 * h:
                continue
            d = hypot(cx, cy)
            tris.append((d, pts, up))
    tris.sort(key=lambda t: t[0])
    step = (rings * h) / rings
    out = []
    for i, (d, pts, up) in enumerate(tris):
        ring = min(int(d / step), rings - 1)
        if ring == 0:
            colour = SORGHUM
        elif ring == 1:
            colour = EMBER if up else SORGHUM
        elif ring == 2:
            colour = CRIMSON if up else EMBER
        elif ring == 3:
            colour = WHITE if up else SORGHUM
        else:
            colour = UMBER if up else WHITE
        poly = " ".join(f"{x + c:.1f},{y + c:.1f}" for x, y in pts)
        shimmer = " s" if ring == rings - 1 and i % 7 == 0 else ""
        out.append(f'<polygon points="{poly}" fill="{colour}" stroke="#6e1715" stroke-width="1.6" stroke-linejoin="round" class="t r{ring}{shimmer}" style="--i:{i}"/>')
    return (f'<svg class="medallion" viewBox="0 0 {size:.0f} {size:.0f}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="A single triangle growing into a woven medallion: an idea becoming a solution">'
            + "".join(out) + "</svg>")


@register.simple_tag
def medallion():
    return mark_safe(_medallion())


@register.simple_tag
def glyph(stage):
    """Small glyphs for the idea → solution caption: 1 = idea, 2 = shaped, 3 = solution."""
    if stage == 1:
        body = f'<polygon points="12,4 20,18 4,18" fill="{SORGHUM}"/>'
    elif stage == 2:
        body = (f'<polygon points="12,2 18,12 6,12" fill="{SORGHUM}"/><polygon points="6,12 12,22 0,22" fill="{EMBER}"/>'
                f'<polygon points="18,12 24,22 12,22" fill="{EMBER}"/>')
    else:  # a small hexagon of six triangles
        from math import cos, pi, sin
        pts = [(12 + 10 * cos(pi / 3 * k - pi / 2), 12 + 10 * sin(pi / 3 * k - pi / 2)) for k in range(6)]
        body = "".join(
            f'<polygon points="12,12 {pts[k][0]:.1f},{pts[k][1]:.1f} {pts[(k + 1) % 6][0]:.1f},{pts[(k + 1) % 6][1]:.1f}" '
            f'fill="{(SORGHUM, EMBER, CRIMSON)[k % 3]}" stroke="#6e1715" stroke-width="0.8"/>' for k in range(6))
    return mark_safe(f'<svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">{body}</svg>')


# Line icons for the sidebar, drawn on a 24px grid with a 1.75 stroke.
ICONS = {
    "ideas": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z"/>',
    "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 11h6M9 15h4"/>',
    "filter": '<path d="M4 5h16l-6 7.5V19l-4 2v-8.5L4 5Z"/>',
    "scale": '<path d="M12 4v16M7 20h10M5 7h14"/><path d="m5 7-3 6a3 3 0 0 0 6 0L5 7ZM19 7l-3 6a3 3 0 0 0 6 0l-3-6Z"/>',
    "radar": '<path d="m12 3 8.5 6.2-3.3 10H6.8L3.5 9.2 12 3Z"/><path d="m12 8 4 3-1.5 4.5h-5L8 11l4-3Z"/>',
    "columns": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
    "chart": '<path d="M4 4v16h16"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "chat": '<path d="M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z"/>',
    "lifebuoy": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="m5.6 5.6 4 4M14.4 14.4l4 4M18.4 5.6l-4 4M9.6 14.4l-4 4"/>',
    "idcard": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M6 16c.5-1.5 1.6-2 3-2s2.5.5 3 2M15 10h3M15 13h3"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v2.5M12 19v2.5M4.6 4.6l1.8 1.8M17.6 17.6l1.8 1.8M2.5 12H5M19 12h2.5M4.6 19.4l1.8-1.8M17.6 6.4l1.8-1.8"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.4M12 17h.01"/>',
    "bell": '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20c1.2-3.5 4-5 7.5-5s6.3 1.5 7.5 5"/>',
    "logout": '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h10"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}


@register.simple_tag
def icon(name, size=20):
    body = ICONS.get(name, ICONS["file"])
    return mark_safe(
        f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )
