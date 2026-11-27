#!/usr/bin/env python3
"""
running-card.py
===============
Generate a transparent-background PNG with running stats and optional route.

Stats are shown with white text + black outline, in order:
  Distance → Time → Pace or Speed → Elevation gain → Route (if available) → Elevation graph (if available)

The third stat is a toggle. Use pace (min/km) for running or speed (km/h) for cycling.

Layout can be vertical (top-to-bottom) or horizontal (left-to-right).

Usage
-----
Interactive prompt (no route):
    python running-card.py
    python running-card.py --layout h
    python running-card.py --width 1920 --height 1080

From a GPX or FIT file:
    python running-card.py my_run.gpx
    python running-card.py my_run.fit --layout h --width 1280 --height 400

The output file name is the input file name with a .png ending
(my_run.gpx -> my_run.png).  Use --output to set another path.

All options:
    FILE                GPX or FIT file to read stats + route from (optional)
    --distance-source {gps,footpod}  Distance source for FIT files (default: footpod)
    --pace-source {gps,footpod}      Pace source for FIT files (default: footpod)
    --metric {pace,speed}            show pace (min/km) or speed (km/h) (default: pace)
    --layout v|h        vertical (default) or horizontal layout
    --width  N          canvas width  in pixels (default 1200 vertical, 3200 horizontal)
    --height N          canvas height in pixels (default auto)
    --outline-width PX  text outline width in pixels (default: 0; 0 disables)
    --ele-band M        elevation hysteresis band in metres (default 1.0, matches Garmin)
                        use ~8.0 to match Runalyze's more aggressive noise filtering
    --output PATH       output PNG path (default: input file name with .png ending)

Dependencies:
    pip install Pillow
    pip install fitparse    # only for FIT files

"""

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("Missing: pip install Pillow")

# ---------------------------------------------------------------------------
# GPX parsing (pure stdlib – no gpxpy needed)
# ---------------------------------------------------------------------------

def _ns(tag, ns):
    return f"{{{ns}}}{tag}"

def _elevation_gain_hysteresis(elevations: list, band: float) -> float:
    """Calculate total elevation gain using a hysteresis band to filter GPS noise.

    Only counts a climb once the elevation has risen at least `band` metres
    above the most recent low point. This matches how Garmin Connect calculates
    elevation gain (band ≈ 1 m) and suppresses the spurious micro-oscillations
    that a naive point-to-point sum accumulates.

    band=1.0  → ~132 m on the test file  (matches Garmin Connect)
    band=8.0  → ~89 m  on the test file  (close to Runalyze)
    """
    if not elevations:
        return 0.0
    gain = 0.0
    low  = elevations[0]
    for e in elevations[1:]:
        if e < low:
            low = e
        elif e - low >= band:
            gain += e - low
            low   = e
    return gain


def parse_gpx(path: str, ele_band: float = 1.0):
    """Parse a GPX file. Returns (total_seconds, distance_km, elevation_gain_m, norm_points, elevations).
    norm_points is a list of (x, y) in [0,1] with north-up, or [] if no track.
    elevations is a list of raw elevation values (metres) per track point, or []."""
    tree = ET.parse(path)
    root = tree.getroot()

    # Detect namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0][1:]

    def find_all(elem, tag):
        if ns:
            return elem.iter(_ns(tag, ns))
        return elem.iter(tag)

    points = []
    for trkpt in find_all(root, "trkpt"):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        time_el = trkpt.find(_ns("time", ns)) if ns else trkpt.find("time")
        time_str = time_el.text.strip() if time_el is not None else None
        ele_el = trkpt.find(_ns("ele", ns)) if ns else trkpt.find("ele")
        ele = float(ele_el.text.strip()) if ele_el is not None else None
        points.append((lat, lon, time_str, ele))

    if not points:
        return 0, 0.0, 0.0, [], []

    # Distance via Haversine
    def haversine(lat1, lon1, lat2, lon2):
        R = 6_371_000
        f1, f2 = math.radians(lat1), math.radians(lat2)
        df = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(df/2)**2 + math.cos(f1)*math.cos(f2)*math.sin(dl/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    dist_m = sum(
        haversine(points[i-1][0], points[i-1][1], points[i][0], points[i][1])
        for i in range(1, len(points))
    )
    distance_km = dist_m / 1000.0

    # Duration from timestamps
    total_seconds = 0
    t0, t1 = points[0][2], points[-1][2]
    if t0 and t1:
        def parse_iso(s):
            # Handle Z and +00:00
            s = s.replace("Z", "+00:00")
            from datetime import datetime, timezone
            try:
                return datetime.fromisoformat(s)
            except Exception:
                # fallback: strip timezone
                return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        try:
            total_seconds = int((parse_iso(t1) - parse_iso(t0)).total_seconds())
        except Exception:
            pass

    # Elevation gain using hysteresis to filter GPS noise
    elevs = [p[3] for p in points if p[3] is not None]
    elevation_gain_m = _elevation_gain_hysteresis(elevs, band=ele_band)

    # Normalise to [0,1] keeping aspect ratio (north-up)
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat_span = max_lat - min_lat or 1e-9
    lon_span = max_lon - min_lon or 1e-9

    norm = [
        ((p[1] - min_lon) / lon_span,
         1.0 - (p[0] - min_lat) / lat_span)
        for p in points
    ]
    raw_elevations = [p[3] for p in points if p[3] is not None]
    return total_seconds, distance_km, elevation_gain_m, norm, raw_elevations


def _fit_semicircles_to_degrees(value: float) -> float:
    return value * 180.0 / (2**31)


def parse_fit(path: str, ele_band: float = 1.0, distance_source: str = "footpod", pace_source: str = "footpod"):
    """Parse a FIT file. Returns (total_seconds, distance_km, elevation_gain_m, norm_points, elevations, pace_min_km)."""
    try:
        from fitparse import FitFile
    except ImportError:
        sys.exit("Missing: pip install Pillow fitparse")

    fitfile = FitFile(path)
    records = []
    gps_distance_m = None
    footpod_distance_m = None
    footpod_speeds_mps = []
    first_time = None
    last_time = None

    for msg in fitfile.get_messages():
        if msg.name != "record":
            continue

        fields = {field.name: field.value for field in msg}
        lat = fields.get("position_lat")
        lon = fields.get("position_long")
        if lat is not None and lon is not None:
            lat = _fit_semicircles_to_degrees(lat)
            lon = _fit_semicircles_to_degrees(lon)

        timestamp = fields.get("timestamp")
        if timestamp is not None:
            if first_time is None:
                first_time = timestamp
            last_time = timestamp
            time_str = timestamp.isoformat()
        else:
            time_str = None

        ele = fields.get("enhanced_altitude")
        if ele is None:
            ele = fields.get("altitude")
        if ele is not None:
            ele = float(ele)

        distance = fields.get("distance")
        if distance is not None:
            footpod_distance_m = float(distance)

        speed = fields.get("enhanced_speed")
        if speed is None:
            speed = fields.get("speed")
        if speed is not None:
            footpod_speeds_mps.append(float(speed))

        records.append((lat, lon, time_str, ele))

    if not records:
        return 0, 0.0, 0.0, [], [], None

    def haversine(lat1, lon1, lat2, lon2):
        R = 6_371_000
        f1, f2 = math.radians(lat1), math.radians(lat2)
        df = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(df/2)**2 + math.cos(f1)*math.cos(f2)*math.sin(dl/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    pos_records = [p for p in records if p[0] is not None and p[1] is not None]
    if len(pos_records) >= 2:
        gps_distance_m = sum(
            haversine(pos_records[i-1][0], pos_records[i-1][1], pos_records[i][0], pos_records[i][1])
            for i in range(1, len(pos_records))
        )

    if distance_source == "footpod" and footpod_distance_m is not None:
        distance_km = footpod_distance_m / 1000.0
    elif gps_distance_m is not None:
        distance_km = gps_distance_m / 1000.0
    else:
        distance_km = 0.0

    total_seconds = 0
    if first_time is not None and last_time is not None:
        try:
            total_seconds = int((last_time - first_time).total_seconds())
        except Exception:
            total_seconds = 0

    elevs = [p[3] for p in records if p[3] is not None]
    elevation_gain_m = _elevation_gain_hysteresis(elevs, band=ele_band)

    if pos_records:
        lats = [p[0] for p in pos_records]
        lons = [p[1] for p in pos_records]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        lat_span = max_lat - min_lat or 1e-9
        lon_span = max_lon - min_lon or 1e-9
        norm = [
            ((p[1] - min_lon) / lon_span,
             1.0 - (p[0] - min_lat) / lat_span)
            for p in pos_records
        ]
    else:
        norm = []

    if pace_source == "footpod" and footpod_speeds_mps:
        avg_speed_mps = sum(footpod_speeds_mps) / len(footpod_speeds_mps)
        pace_min_km = (60.0 / (avg_speed_mps * 3.6)) if avg_speed_mps > 0 else None
    elif pace_source == "footpod" and distance_km > 0 and total_seconds > 0:
        pace_min_km = total_seconds / 60.0 / distance_km
    else:
        pace_min_km = None

    raw_elevations = elevs
    return total_seconds, distance_km, elevation_gain_m, norm, raw_elevations, pace_min_km


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_pace(total_seconds: int, distance_km: float) -> str:
    if distance_km <= 0:
        return "--:--"
    spk = total_seconds / distance_km
    m, s = int(spk) // 60, int(spk) % 60
    return f"{m}:{s:02d}"


def fmt_pace_value(pace_min_km: float | None) -> str:
    if pace_min_km is None or pace_min_km <= 0:
        return "--:--"
    minutes = int(pace_min_km)
    seconds = int(round((pace_min_km - minutes) * 60))
    if seconds >= 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def fmt_speed(total_seconds: int, distance_km: float) -> str:
    """Average speed in km/h from duration and distance."""
    if total_seconds <= 0 or distance_km <= 0:
        return "--"
    kph = distance_km / (total_seconds / 3600.0)
    return f"{kph:.1f}"


def fmt_speed_value(pace_min_km: float | None) -> str:
    """Convert an average pace in min/km to speed in km/h."""
    if pace_min_km is None or pace_min_km <= 0:
        return "--"
    return f"{60.0 / pace_min_km:.1f}"


def parse_time_input(text: str) -> int:
    parts = text.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0])*60 + int(parts[1])
        return int(parts[0])
    except ValueError:
        raise ValueError(f"Cannot parse '{text}'. Use HH:MM:SS or MM:SS.")


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
]
FONT_CANDIDATES_REG = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a TrueType face. Bold falls back to any bold face on the system."""
    for path in (FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REG):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    if bold:
        # Last resort: ask fontconfig for any installed bold sans-serif face.
        try:
            import subprocess
            fc = subprocess.run(
                ["fc-match", "-f", "%{file}", "sans-serif:bold"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if fc:
                return ImageFont.truetype(fc, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text rendering with outline
# ---------------------------------------------------------------------------

def draw_outlined_text(draw: ImageDraw.ImageDraw, pos, text: str,
                       font, fill=(255,255,255), outline=(0,0,0), outline_width=2):
    draw.text(
        pos,
        text,
        font=font,
        fill=fill,
        stroke_width=max(0, outline_width),
        stroke_fill=outline,
    )


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


# ---------------------------------------------------------------------------
# Route drawing
# ---------------------------------------------------------------------------

def render_route(norm_points, width: int, height: int) -> Image.Image:
    """Render the route onto a transparent RGBA image of given size."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if len(norm_points) < 2:
        return img

    # Supersampling for smooth lines
    S = 10
    layer = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    margin = 0.06  # fraction of dimension
    mx = width  * S * margin
    my = height * S * margin
    iw = width  * S * (1 - 2 * margin)
    ih = height * S * (1 - 2 * margin)

    def to_px(nx, ny):
        return (int(mx + nx * iw), int(my + ny * ih))

    pts = [to_px(x, y) for x, y in norm_points]

    # Shadow
    for i in range(1, len(pts)):
        ld.line([pts[i-1], pts[i]], fill=(0, 0, 0, 55), width=10)

    # Main line — white with black outline effect via layering
    line_w = 90
    #black outlines?
    #for i in range(1, len(pts)):
    #    ld.line([pts[i-1], pts[i]], fill=(0, 0, 0, 200), width=line_w + 4)
    for i in range(1, len(pts)):
        #ld.line([pts[i-1], pts[i]], fill=(255, 255, 255, 230), width=line_w) #white
        ld.line([pts[i-1], pts[i]], fill=(252, 82, 2, 255), width=line_w) #orange

    # Start and finish markers (drawn in supersampled space, then scaled down)
    def draw_start_marker(cx, cy, r):
        ld.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(0, 0, 0, 230))
        ri = r - max(4, r // 5)
        ld.ellipse([cx-ri, cy-ri, cx+ri, cy+ri], fill=(255, 255, 255, 255))

    def draw_finish_marker(cx, cy, r):
        """Black/white checkered finish disc with a white rim."""
        cx, cy, r = int(cx), int(cy), int(r)
        n = 2 * r + 1
        grid = 3
        tile = n / grid
        plate = Image.new("RGBA", (n, n), (255, 255, 255, 255))
        pd = ImageDraw.Draw(plate)
        for i in range(grid):
            for j in range(grid):
                if (i + j) % 2:
                    pd.rectangle([i * tile, j * tile,
                                  (i + 1) * tile - 1, (j + 1) * tile - 1],
                                 fill=(0, 0, 0, 255))

        mask = Image.new("L", (n, n), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, n - 1, n - 1], fill=255)

        x0, y0 = int(round(cx - r)), int(round(cy - r))
        rim = max(4, r // 6)
        # White rim behind the checker plate
        ld.ellipse([x0 - rim, y0 - rim, x0 + n + rim - 1, y0 + n + rim - 1],
                   fill=(255, 255, 255, 255))
        layer.paste(plate, (x0, y0), mask)
        ld.ellipse([x0, y0, x0 + n - 1, y0 + n - 1],
                   outline=(0, 0, 0, 255), width=max(2, r // 8))

    draw_start_marker(*pts[0], 12 * S)
    draw_finish_marker(*pts[-1], 15 * S)

    layer = layer.resize((width, height), Image.LANCZOS)
    return layer



# ---------------------------------------------------------------------------
# Elevation graph drawing
# ---------------------------------------------------------------------------

def render_elevation_graph(
    elevations: list,
    width: int,
    height: int,
    outline_width: int | None = None,
) -> Image.Image:
    """Render a filled elevation profile onto a transparent RGBA image."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if len(elevations) < 2:
        return img

    S = 12  # Match route supersampling for consistent stroke rendering.
    layer = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    # Pre-load font here so we can measure label height for margins
    label_font_size = max(10, height // 10)
    try:
        label_font = load_font(label_font_size * S, bold=True)
    except Exception:
        label_font = ImageFont.load_default()

    _probe_img = Image.new("RGBA", (1, 1))
    _probe_drw = ImageDraw.Draw(_probe_img)
    _bb = _probe_drw.textbbox((0, 0), "000m", font=label_font)
    label_h = _bb[3] - _bb[1]

    margin_x      = int(width * S * 0.04)
    margin_top    = label_h + 4 * S   # space for max label above the peak
    margin_bottom = label_h + 12 * S   # space for min label below the baseline
    iw = width  * S - 2 * margin_x
    ih = height * S - margin_top - margin_bottom

    min_e = min(elevations)
    max_e = max(elevations)
    span_e = max_e - min_e or 1.0

    n = len(elevations)

    def to_px(i, e):
        x = margin_x + int(i / (n - 1) * iw)
        y = margin_top + int((1.0 - (e - min_e) / span_e) * ih)
        return x, y

    pts = [to_px(i, e) for i, e in enumerate(elevations)]

    # Build filled polygon (profile + bottom baseline)
    baseline_y = margin_top + ih
    poly = pts + [(pts[-1][0], baseline_y), (pts[0][0], baseline_y)]

    # Filled area — semi-transparent white
    #ld.polygon(poly, fill=(255, 255, 255, 55))

    # Match the GPS route's shadow, dark rim, and orange core.
    #for i in range(1, len(pts)):
    #    ld.line([pts[i-1], pts[i]], fill=(0, 0, 0, 55), width=10)
    line_w = 108
    #for i in range(1, len(pts)):
    #    ld.line([pts[i-1], pts[i]], fill=(0, 0, 0, 200), width=line_w + 4)
    for i in range(1, len(pts)):
        ld.line([pts[i-1], pts[i]], fill=(252, 82, 2, 255), width=line_w)

    # Baseline
    #ld.line([(margin_x, baseline_y), (margin_x + iw, baseline_y)], fill=(255, 255, 255, 255), width=max(2, S))

    canvas_w_s = width  * S
    canvas_h_s = height * S
    pad_s = max(4, S * 2)
    label_outline_width = (
        max(2, label_font_size * S // 10)
        if outline_width is None else outline_width * S
    )
    label_inset = pad_s + label_outline_width

    def label_size(text):
        bb = ld.textbbox((0, 0), text, font=label_font)
        return bb[2] - bb[0], bb[3] - bb[1]

    def clamp_label(x, y, lw, lh):
        """Clamp label top-left so the full label fits within the supersampled canvas."""
        x = max(label_inset, min(x, canvas_w_s - lw - label_inset))
        y = max(label_inset, min(y, canvas_h_s - lh - label_inset))
        return x, y

    def draw_elev_label(draw, pos, text):
        x, y = pos
        bbox = draw.textbbox((0, 0), text, font=label_font)
        text_x, text_y = x - bbox[0], y - bbox[1]
        draw.text(
            (text_x, text_y),
            text,
            font=label_font,
            fill=(255, 255, 255, 255),
            stroke_width=max(0, label_outline_width),
            stroke_fill=(0, 0, 0, 255),
        )

    # Max label — above the highest point, clamped inside the image
    max_i = elevations.index(max_e)
    mx, my = to_px(max_i, max_e)
    max_text = f"{max_e:.0f}m"
    mlw, mlh = label_size(max_text)
    lx_max, ly_max = clamp_label(mx - mlw // 2, my - mlh - 4 * S, mlw, mlh)
    draw_elev_label(ld, (lx_max, ly_max), max_text)

    # Min label — below the lowest point, clamped inside the image
    min_i = elevations.index(min_e)
    nx, ny = to_px(min_i, min_e)
    min_text = f"{min_e:.0f}m"
    nlw, nlh = label_size(min_text)
    lx_min, ly_min = clamp_label(nx - nlw // 2, ny + 4 * S, nlw, nlh)
    draw_elev_label(ld, (lx_min, ly_min), min_text)

    layer = layer.resize((width, height), Image.LANCZOS)
    return layer



def generate_card(
    total_seconds: int,
    distance_km: float,
    elevation_gain_m: float = 0.0,
    norm_points=None,
    elevations=None,
    layout: str = "v",       # "v" = vertical, "h" = horizontal
    width: int = None,
    height: int = None,
    output: str = "running_card.png",
    pace_min_km: float | None = None,
    metric: str = "pace",    # "pace" = min/km, "speed" = km/h
    outline_width: int | None = None,
):
    if metric not in ("pace", "speed"):
        raise ValueError(f"Unknown metric '{metric}'. Use 'pace' or 'speed'.")
    has_route = bool(norm_points and len(norm_points) >= 2)
    has_ele_graph = bool(elevations and len(elevations) >= 2)
    label_outline_width = 2 if outline_width is None else outline_width
    value_outline_width = 3 if outline_width is None else outline_width

    # ---------- sizing ----------
    # We build everything relative to a "unit" derived from the requested size.
    # Default canvas sizes if not specified:
    if layout == "v":
        canvas_w = width  or 1200
        # height determined by content below
    else:
        canvas_w = width  or 3200

    # Probe draw surface to measure text
    probe = Image.new("RGBA", (1, 1))
    probe_draw = ImageDraw.Draw(probe)

    # Choose font size relative to canvas width
    if layout == "v":
        value_fs = max(32, canvas_w // 8)
        label_fs = max(12, canvas_w // 30)
        unit_fs  = max(14, canvas_w // 22)
        pad      = max(16, canvas_w // 24)
    else:
        value_fs = max(32, canvas_w // 18)
        label_fs = max(11, canvas_w // 68)
        unit_fs  = max(12, canvas_w // 50)
        pad      = max(12, canvas_w // 60)
    stat_gap = pad * 2

    f_value = load_font(value_fs, bold=True)
    f_label = load_font(label_fs, bold=True)
    f_unit  = load_font(unit_fs,  bold=True)

    pace_text = fmt_pace_value(pace_min_km) if pace_min_km is not None else fmt_pace(total_seconds, distance_km)
    speed_text = fmt_speed_value(pace_min_km) if pace_min_km is not None else fmt_speed(total_seconds, distance_km)
    if metric == "speed":
        third_stat = ("SPEED", speed_text, "km/h")
    else:
        third_stat = ("PACE", pace_text, "/km")
    stats = [
        ("DISTANCE", f"{distance_km:.2f}", "km"),
        ("TIME",     fmt_duration(total_seconds), ""),
        third_stat,
        ("ELEVATION", f"{elevation_gain_m:.0f}", "m"),
    ]

    # Measure each stat block
    def measure_stat(label, value, unit):
        lw, lh = text_size(probe_draw, label, f_label)
        vw, vh = text_size(probe_draw, value, f_value)
        uw, uh = text_size(probe_draw, unit,  f_unit) if unit else (0, 0)
        return lw, lh, vw, vh, uw, uh

    measurements = [measure_stat(*s) for s in stats]

    # ---------- layout: vertical ----------
    if layout == "v":
        # Each stat occupies a row: label on left, value+unit on right
        # OR stacked: label top, value bottom — we do stacked (like Strava app)
        stat_heights = []
        for lw, lh, vw, vh, uw, uh in measurements:
            stat_heights.append(lh + pad // 2 + vh)

        stat_w = canvas_w - 2 * pad

        # Route area: square-ish, same width
        route_h = canvas_w if has_route else 0

        # Elevation graph: 1/3 of canvas width tall
        ele_graph_h = (canvas_w // 3) if has_ele_graph else 0

        total_h = (
            pad                                          # top padding
            + sum(stat_heights)
            + stat_gap * (len(stats) - 1)               # gaps between stats
            + (pad * 2 + route_h if has_route else 0)   # route block
            + (pad * 2 + ele_graph_h if has_ele_graph else 0)  # elevation graph
            + pad                                        # bottom padding
        )
        canvas_h = height or total_h
        canvas   = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw     = ImageDraw.Draw(canvas)

        y = pad
        for i, (label, value, unit) in enumerate(stats):
            lw, lh, vw, vh, uw, uh = measurements[i]

            # Center the label and value block
            label_x = (canvas_w - lw) // 2
            draw_outlined_text(draw, (label_x, y), label, f_label,
                                fill=(255,255,255), outline=(0,0,0), outline_width=label_outline_width)
            y += lh + pad // 4

            value_x = (canvas_w - (vw + (pad // 3 + uw if unit else 0))) // 2
            draw_outlined_text(draw, (value_x, y), value, f_value,
                                fill=(255,255,255), outline=(0,0,0), outline_width=value_outline_width)
            if unit:
                ux = value_x + vw + pad // 3
                # align unit baseline with value
                uy = y + vh - uh
                draw_outlined_text(draw, (ux, uy), unit, f_unit,
                                   fill=(255,255,255,200), outline=(0,0,0), outline_width=label_outline_width)
            y += vh
            if i < len(stats) - 1:
                y += stat_gap

        # Route
        if has_route:
            y += pad // 2
            route_img = render_route(norm_points, canvas_w - 2*pad, route_h)
            canvas.paste(route_img, (pad, y), route_img)
            y += route_h

        # Elevation graph
        if has_ele_graph:
            y += pad
            ele_img = render_elevation_graph(
                elevations, canvas_w - 2*pad, ele_graph_h, outline_width
            )
            canvas.paste(ele_img, (pad, y), ele_img)

    # ---------- layout: horizontal ----------
    else:
        # Stats side by side, route on the right (if available)
        # Each stat column: label top, value bottom
        col_widths = []
        for lw, lh, vw, vh, uw, uh in measurements:
            col_w = max(lw, vw + (pad // 2 + uw if uw else 0))
            col_widths.append(col_w)

        stats_total_w = sum(col_widths) + stat_gap * (len(stats) - 1)
        max_stat_h    = max(lh + pad // 2 + vh for lw, lh, vw, vh, uw, uh in measurements)

        # Route: fixed fraction of total width
        if has_route:
            route_w = canvas_w - stats_total_w - 3 * pad
            route_h = max_stat_h + 2 * pad
        else:
            route_w = 0
            route_h = 0

        canvas_h = height or (max_stat_h + 2 * pad)

        # Elevation graph sits below everything in horizontal layout
        ele_graph_h = (canvas_h // 2) if has_ele_graph else 0
        if has_ele_graph:
            canvas_h_total = canvas_h + pad + ele_graph_h + pad
        else:
            canvas_h_total = canvas_h

        canvas   = Image.new("RGBA", (canvas_w, canvas_h_total), (0, 0, 0, 0))
        draw     = ImageDraw.Draw(canvas)

        x = pad
        for i, (label, value, unit) in enumerate(stats):
            lw, lh, vw, vh, uw, uh = measurements[i]

            # Vertically centre the stat block in the canvas
            block_h = lh + pad // 4 + vh
            y_off   = (canvas_h - block_h) // 2

            # Horizontally centre text within its stat column
            total_w = vw + (pad // 3 + uw if unit else 0)
            label_x = x + (col_widths[i] - lw) // 2
            value_x = x + (col_widths[i] - total_w) // 2

            draw_outlined_text(draw, (label_x, y_off), label, f_label,
                                fill=(255,255,255), outline=(0,0,0), outline_width=label_outline_width)
            draw_outlined_text(draw, (value_x, y_off + lh + pad // 4), value, f_value,
                                fill=(255,255,255), outline=(0,0,0), outline_width=value_outline_width)
            if unit:
                ux = value_x + vw + pad // 3
                uy = y_off + lh + pad // 4 + vh - uh
                draw_outlined_text(draw, (ux, uy), unit, f_unit,
                                   fill=(255,255,255,200), outline=(0,0,0), outline_width=label_outline_width)

            x += col_widths[i] + stat_gap

        # Separator
        if has_route:
            sx = x - pad // 2
            draw.line([(sx, pad), (sx, canvas_h - pad)], fill=(255,255,255,80), width=1)

        # Route on the right
        if has_route:
            rx = x
            ry = (canvas_h - route_h) // 2
            rw = canvas_w - rx - pad
            rh = route_h
            route_img = render_route(norm_points, rw, rh)
            canvas.paste(route_img, (rx, ry), route_img)

        # Elevation graph below the stats row
        if has_ele_graph:
            ey = canvas_h + pad
            ele_img = render_elevation_graph(
                elevations, canvas_w - 2*pad, ele_graph_h, outline_width
            )
            canvas.paste(ele_img, (pad, ey), ele_img)

    canvas.save(output, "PNG")
    print(f"✓ Saved: {output}  ({canvas.width}×{canvas.height} px)")


# ---------------------------------------------------------------------------
# Interactive prompt
# ---------------------------------------------------------------------------

def enable_line_editing() -> None:
    """Python only gives scripts readline editing when interactive, so turn it on."""
    try:
        import readline
    except ImportError:
        return
    readline.parse_and_bind(r'"\C-h": unix-word-rubout')
    readline.parse_and_bind(r'"\C-w": unix-word-rubout')


def prompt_manual():
    enable_line_editing()
    print("\n── Running Card Generator ──")
    while True:
        t = input("Total time (HH:MM:SS or MM:SS): ").strip()
        try:
            total_seconds = parse_time_input(t)
            break
        except ValueError as e:
            print(f"  ⚠ {e}")
    while True:
        d = input("Distance (km): ").strip().replace(",", ".")
        try:
            distance_km = float(d)
            break
        except ValueError:
            print("  ⚠ Please enter a number, e.g. 10.5")
    while True:
        e = input("Elevation gain (m) [0]: ").strip().replace(",", ".")
        if e == "":
            elevation_gain_m = 0.0
            break
        try:
            elevation_gain_m = float(e)
            break
        except ValueError:
            print("  ⚠ Please enter a number, e.g. 320")
    return total_seconds, distance_km, elevation_gain_m


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Generate a transparent-background PNG running card.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input",      metavar="FILE",  nargs="?",
                   help="GPX or FIT file (extracts stats + route; default: interactive prompt)")
    p.add_argument("--distance-source", default="footpod", choices=["gps", "footpod"],
                   help="Distance source for FIT files (default: footpod)")
    p.add_argument("--pace-source", default="footpod", choices=["gps", "footpod"],
                   help="Pace source for FIT files (default: footpod)")
    p.add_argument("--metric", default="pace", choices=["pace", "speed"],
                   help="show pace in min/km (default) or speed in km/h, for cycling")
    p.add_argument("--layout",   metavar="v|h",   default="v",
                   choices=["v","h"], help="vertical (v) or horizontal (h) layout")
    p.add_argument("--width",    metavar="PX",    type=int, help="canvas width in pixels")
    p.add_argument("--height",   metavar="PX",    type=int, help="canvas height in pixels")
    p.add_argument("--outline-width", metavar="PX", type=int, default=0,
                   help="text outline width in pixels (default: 0; 0 disables)")
    p.add_argument("--ele-band", metavar="M",     type=float, default=1.0,
                   dest="ele_band",
                   help="elevation hysteresis band in metres (default 1.0 ≈ Garmin; 8.0 ≈ Runalyze)")
    p.add_argument("--output",   metavar="FILE",  default=None,
                   help="output PNG path (default: input file name with .png ending)")
    args = p.parse_args()
    if args.outline_width is not None and args.outline_width < 0:
        p.error("--outline-width must be non-negative")

    norm_points = None
    elevations = None
    elevation_gain_m = 0.0
    pace_min_km = None

    if args.input:
        path = Path(args.input)
        if not path.exists():
            sys.exit(f"File not found: {args.input}")
        suffix = path.suffix.lower()
        if suffix == ".fit":
            print(f"Reading FIT: {args.input}")
            total_seconds, distance_km, elevation_gain_m, norm_points, elevations, pace_min_km = parse_fit(
                args.input,
                ele_band=args.ele_band,
                distance_source=args.distance_source,
                pace_source=args.pace_source,
            )
        else:
            print(f"Reading GPX: {args.input}")
            total_seconds, distance_km, elevation_gain_m, norm_points, elevations = parse_gpx(args.input, ele_band=args.ele_band)
        print(f"  Distance  : {distance_km:.2f} km")
        print(f"  Duration  : {fmt_duration(total_seconds)}")
        pace_text = fmt_pace_value(pace_min_km) if pace_min_km is not None else fmt_pace(total_seconds, distance_km)
        if args.metric == "speed":
            speed_text = fmt_speed_value(pace_min_km) if pace_min_km is not None else fmt_speed(total_seconds, distance_km)
            print(f"  Avg speed : {speed_text} km/h")
        else:
            print(f"  Avg pace  : {pace_text} /km")
        print(f"  Elevation : +{elevation_gain_m:.0f} m")
        print(f"  Points    : {len(norm_points)}")
    else:
        total_seconds, distance_km, elevation_gain_m = prompt_manual()

    if args.input:
        output = args.output or str(Path(args.input).with_suffix(".png"))
    else:
        output = args.output or "running_card.png"

    generate_card(
        total_seconds=total_seconds,
        distance_km=distance_km,
        elevation_gain_m=elevation_gain_m,
        norm_points=norm_points,
        elevations=elevations,
        layout=args.layout,
        width=args.width,
        height=args.height,
        output=output,
        pace_min_km=pace_min_km,
        metric=args.metric,
        outline_width=args.outline_width,
    )


if __name__ == "__main__":
    main()
