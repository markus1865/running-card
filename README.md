# running-card

Generate a transparent PNG card with running or cycling stats. The tool reads a
GPX or FIT file and draws the route and the elevation profile.

The card is made for overlay on a photo or a video. The background stays
transparent, and the text is white with a black outline.

## What the card shows

The stats appear in this order:

1. Distance in kilometres.
2. Total time from the first to the last track point, as `HH:MM:SS` or
   `MM:SS`.
3. Pace in `min/km`, or speed in `km/h`.
4. Elevation gain in metres.
5. The GPS route, when the file has position data.
6. The elevation profile, when the file has altitude data.

## Layouts

The vertical layout stacks the stats from top to bottom. The route is a square
block below the stats. The elevation profile sits below the route.

The horizontal layout puts the stats in one row. Use it for wide banners and
video lower thirds.

## Requirements

1. Python 3.10 or later.
2. Pillow.
3. fontconfig, on Linux, for the font fallback.
4. fitparse, only for FIT files.
5. A TrueType font. The tool tries Liberation, DejaVu, FreeFont, Noto, Arial,
   and Helvetica, in this order.

## Install

```
pip install Pillow
pip install fitparse    # only for FIT files
```

GPX files need no extra package. The GPX reader uses the Python standard
library.

## Use

Read a file:

```
python running-card.py my_run.gpx
python running-card.py my_run.fit
```

The tool writes `my_run.png` next to the input file. Use `--output` to set
another path.

Enter the stats by hand:

```
python running-card.py
```

The tool asks for the time, the distance, and the elevation gain. It writes
`running_card.png`.

Set the size and the layout:

```
python running-card.py my_run.gpx --layout h --width 1920 --height 600
python running-card.py my_run.fit --metric speed --width 1200
```

## Options

| Option | Value | Default | Effect |
| --- | --- | --- | --- |
| `FILE` | path | none | GPX or FIT file to read. When you omit it, the tool asks for the stats by hand. |
| `--metric` | `pace`, `speed` | `pace` | Shows pace in min/km or speed in km/h. Use `speed` for cycling. |
| `--layout` | `v`, `h` | `v` | Vertical or horizontal layout. |
| `--width` | pixels | 1200 for `v`, 3200 for `h` | Canvas width. |
| `--height` | pixels | auto | Canvas height. When you omit it, the tool calculates the height from the content. |
| `--distance-source` | `gps`, `footpod` | `footpod` | Distance source for FIT files. |
| `--pace-source` | `gps`, `footpod` | `footpod` | Pace source for FIT files. |
| `--ele-band` | metres | `1.0` | Elevation hysteresis band. See the note below. |
| `--outline-width` | pixels | `0` | Text outline width. `0` turns the outline off. |
| `--output` | path | input name with `.png` | Output PNG path. |

## Elevation gain

The tool does not add up each height change. A GPS track has small height
noise, and a simple sum adds this noise to the result. The tool counts a climb
only after the track rises above the last low point by a set band.

1. `--ele-band 1.0` matches Garmin Connect.
2. `--ele-band 8.0` matches the stronger noise filter of Runalyze, and gives a
   lower value.

## Colour and transparency

The route line and the elevation profile use Strava orange (`#FC5202`). The
route has a white start disc and a checkered finish disc. The text is white.
All other pixels are transparent, so you can place the PNG on any background,
and you can put it in a video editor as an overlay.

## Licence

MIT. See `LICENSE`.
