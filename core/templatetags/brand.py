"""Brand artwork drawn in code, so it stays sharp and can be animated with CSS."""
from functools import lru_cache
from math import hypot, sqrt

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

TEAL_LIGHT, EMBER, SORGHUM, CRIMSON, WHITE = "#2a7383", "#f26725", "#faa61c", "#9f2421", "#ffffff"


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
            colour = TEAL_LIGHT if up else WHITE
        poly = " ".join(f"{x + c:.1f},{y + c:.1f}" for x, y in pts)
        shimmer = " s" if ring == rings - 1 and i % 7 == 0 else ""
        out.append(f'<polygon points="{poly}" fill="{colour}" stroke="#134e5a" stroke-width="1.6" stroke-linejoin="round" class="t r{ring}{shimmer}" style="--i:{i}"/>')
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
            f'fill="{(SORGHUM, EMBER, CRIMSON)[k % 3]}" stroke="#134e5a" stroke-width="0.8"/>' for k in range(6))
    return mark_safe(f'<svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">{body}</svg>')
