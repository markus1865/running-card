#!/usr/bin/env python3
"""Build the files in examples/.

Steps:
  1. Write demo.gpx: a made-up 12 km run with a plausible elevation profile.
  2. Run running-card.py for the vertical and the horizontal layout.
  3. Write a preview of each card on a dark background.
  4. Read the real race file and put its card on a race photo.

The cards keep a transparent background. The previews and the setup only show
how a card looks on top of a background, as on a photo or in a video editor.

Run from the repository root:
    python examples/make_examples.py
"""

import math
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BACKGROUNDS = HERE / "backgrounds"

STEP_S = 5
LOOP_FRACTION = 0.97      # stop just before the start, so both markers show
LAT0, LON0 = 48.7800, 9.1800
START = datetime(2026, 11, 22, 9, 12, 0, tzinfo=timezone.utc)
EARTH_R = 6_371_000


def haversine(lat1, lon1, lat2, lon2):
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def loop_shape(n):
    """Closed loop in the range [-1, 1] with a bay and a kink, so it looks real."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * LOOP_FRACTION * i / (n - 1)
        r = 1.0 - 0.18 * math.cos(3 * t) + 0.06 * math.sin(5 * t)
        pts.append((r * math.cos(t), r * math.sin(t)))
    return pts


def write_gpx(path: Path, target_km: float, seconds: int,
              base_ele: float = 498.0, climb: float = 46.0,
              climb2: float = 22.0) -> None:
    n = 1 + seconds // STEP_S
    pts = [(LAT0 + x * 0.030, LON0 + y * 0.0185) for x, y in loop_shape(n)]

    # Scale about the centre until the track has the target length.
    for _ in range(40):
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        latc = (min(lats) + max(lats)) / 2
        lonc = (min(lons) + max(lons)) / 2
        dist = sum(
            haversine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
            for i in range(1, len(pts))
        )
        factor = (target_km * 1000) / dist
        if abs(factor - 1.0) < 0.002:
            break
        pts = [(latc + (la - latc) * factor, lonc + (lo - lonc) * factor) for la, lo in pts]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="running-card"',
        '     xmlns="http://www.topografix.com/GPX/1/1">',
        "  <metadata>",
        f"    <name>{path.stem}</name>",
        "    <time>2026-11-22T09:12:00Z</time>",
        "  </metadata>",
        "  <trk>",
        f"    <name>{path.stem}</name>",
        "    <trkseg>",
    ]
    for i, (lat, lon) in enumerate(pts):
        frac = i / (len(pts) - 1)
        # One long climb, one short climb, and small ground noise.
        ele = (
            base_ele
            + climb * max(0.0, math.sin(math.pi * frac)) ** 2
            + climb2 * max(0.0, math.sin(math.pi * (frac - 0.62) / 0.30)) ** 2
            + 0.8 * math.sin(19 * math.pi * frac)
        )
        when = (START + timedelta(seconds=i * STEP_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(
            f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}">'
            f"<ele>{ele:.1f}</ele><time>{when}</time></trkpt>"
        )
    lines += ["    </trkseg>", "  </trk>", "</gpx>", ""]
    path.write_text("\n".join(lines))
    print(f"wrote {path.relative_to(ROOT)}  ({len(pts)} points)")


def render_card(gpx: Path, out: Path, extra) -> None:
    cmd = [sys.executable, str(ROOT / "running-card.py"), str(gpx), "--output", str(out), *extra]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    print(f"wrote {out.relative_to(ROOT)}")


def gradient(size, top=(18, 24, 36), bottom=(64, 70, 82)) -> Image.Image:
    w, h = size
    bg = Image.new("RGB", (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        bg.putpixel((0, y), tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)))
    return bg.resize((w, h), Image.BILINEAR)


def write_preview(card_path: Path, preview_path: Path) -> None:
    card = Image.open(card_path).convert("RGBA")
    bg = gradient(card.size).convert("RGBA")
    bg.alpha_composite(card)
    bg.convert("RGB").save(preview_path, "PNG", optimize=True)
    print(f"wrote {preview_path.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# A card on a photo
# ---------------------------------------------------------------------------

def fit_cover(img: Image.Image, size) -> Image.Image:
    """Crop the photo to the target aspect ratio, then resize it."""
    tw, th = size
    s = max(tw / img.width, th / img.height)
    w, h = round(img.width * s), round(img.height * s)
    img = img.resize((w, h), Image.LANCZOS)
    left, top = (w - tw) // 2, (h - th) // 2
    return img.crop((left, top, left + tw, top + th))


def place(frame: Image.Image, card_path: Path, x_frac: float,
          width_frac: float, v_align: str = "center",
          v_margin: float = 0.0) -> None:
    """Scale the card to a share of the frame width, then paste it.

    x_frac is the left edge as a share of the frame width. v_align is "top",
    "center", or "bottom". v_margin is the gap to the edge, as a share.
    """
    card = Image.open(card_path).convert("RGBA")
    w = max(1, round(frame.width * width_frac))
    h = max(1, round(card.height * w / card.width))
    card = card.resize((w, h), Image.LANCZOS)
    gap = round(frame.height * v_margin)
    if v_align == "top":
        y = gap
    elif v_align == "bottom":
        y = frame.height - h - gap
    else:
        y = (frame.height - h) // 2
    frame.alpha_composite(card, (round(frame.width * x_frac), max(0, y)))


def write_setup(background: Path, size, card: Path, out: Path,
                x_frac: float, width_frac: float, v_align: str = "center",
                v_margin: float = 0.0) -> None:
    frame = fit_cover(Image.open(background).convert("RGB"), size).convert("RGBA")
    place(frame, card, x_frac, width_frac, v_align, v_margin)
    frame.convert("RGB").save(out, quality=82, optimize=True, progressive=True)
    print(f"wrote {out.relative_to(ROOT)}")


def main() -> None:
    run = HERE / "demo.gpx"
    write_gpx(run, target_km=12.0, seconds=3600)

    vertical = HERE / "vertical.png"
    horizontal = HERE / "horizontal.png"
    # The outline keeps the white text readable on a light background.
    render_card(run, vertical, ["--width", "800", "--outline-width", "4"])
    render_card(run, horizontal,
                ["--layout", "h", "--width", "3200", "--height", "700",
                 "--outline-width", "6"])

    write_preview(vertical, HERE / "vertical-preview.png")
    write_preview(horizontal, HERE / "horizontal-preview.png")

    # The card of a real 10 km race, from the FIT file of the watch.
    race_card = HERE / "race-card.png"
    render_card(HERE / "dagersheim-waldlauf.fit", race_card,
                ["--width", "900", "--outline", "0"])

    # The photo is 2:3. The runner fills the centre and the right side, so the
    # card sits low at the left edge, where the background is free.
    write_setup(BACKGROUNDS / "race-dagersheim.jpg", (2000, 3000), race_card,
                HERE / "setup-race.jpg", x_frac=0.02, width_frac=0.40,
                v_align="bottom", v_margin=0.01)


if __name__ == "__main__":
    main()
