# running-card

Generate a transparent PNG card with running or cycling stats. The tool reads a
GPX or FIT file and draws the route and the elevation profile.

The card is made for overlay on a photo or a video. The background stays
transparent, and the text is white with a black outline.

## Examples

### Cards

These two cards come from `examples/demo.gpx`. The dark background is only for
the preview. The PNG file keeps a transparent background.

Vertical layout, `--width 800`:

<img src="examples/vertical-preview.png" width="300" alt="Vertical card: distance, time, pace, elevation, route, and elevation profile">

Horizontal layout, `--layout h --width 3200 --height 700`:

<img src="examples/horizontal-preview.png" width="820" alt="Horizontal banner: the four stats in one row, the route on the right, and the elevation profile below">

### On a photo

The frame below is a real photo from the Dagersheim forest run. The card comes
from the FIT file of the watch, so the data is real. The card sits on the left
side, clear of the runner.

<img src="examples/setup-race.jpg" width="480" alt="Vertical card on the left of a race photo: 10.28 km, 37:22, 3:38 per km, 56 m of climb">

The card is the same PNG file, so it also goes into a video editor as an
overlay. `make_examples.py` puts the card on the photo with Pillow.

The example cards also use `--outline-width`. The outline keeps the text
readable on a light background. On a photo, `--outline-width 0` gives the text
without an edge.

### Files in `examples/`

1. `demo.gpx`: a 12 km run with 56 m of climb. The track is made up, not a real
   run.
2. `vertical.png` and `horizontal.png`: the cards, with a transparent
   background.
3. `vertical-preview.png` and `horizontal-preview.png`: the cards on a dark
   background.
4. `dagersheim-waldlauf.fit`: the watch file of a real 10 km race.
5. `race-card.png`: the card from that file.
6. `setup-race.jpg`: the card on a race photo. The photo is the author's own.
7. `backgrounds/race-dagersheim.jpg`: the photo without the card.
8. `make_examples.py`: builds the files again. Run
   `python examples/make_examples.py`.

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
video lower thirds. A thin separator line divides the stats from the route.

The route keeps its true shape in both layouts. The tool corrects the length of
a longitude degree for the latitude, so a route does not look stretched.

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
| `--height` | pixels | auto | Canvas height. When you omit it, the tool calculates the height from the content. In the horizontal layout the route uses the full height, so this option also sets the size of the route. |
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
