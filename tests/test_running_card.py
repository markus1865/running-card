"""Tests for running-card.py.

Run from the repository root:
    python -m pytest
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("running_card", ROOT / "running-card.py")
rc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rc)

DEMO_GPX = ROOT / "examples" / "demo.gpx"
RACE_FIT = ROOT / "examples" / "dagersheim-waldlauf.fit"


@pytest.fixture(scope="module")
def demo_gpx():
    return rc.parse_gpx(str(DEMO_GPX))


# ---------------------------------------------------------------------------
# Elevation gain
# ---------------------------------------------------------------------------

def test_elevation_gain_empty():
    assert rc._elevation_gain_hysteresis([], 1.0) == 0.0


def test_elevation_gain_ignores_noise_below_the_band():
    assert rc._elevation_gain_hysteresis([100, 100.5, 100.2, 100.8, 100.4], 1.0) == 0.0


def test_elevation_gain_counts_a_climb():
    assert rc._elevation_gain_hysteresis([100, 101, 102, 103], 1.0) == 3.0


def test_elevation_gain_ignores_a_descent():
    assert rc._elevation_gain_hysteresis([100, 90, 91, 92], 1.0) == 2.0


def test_elevation_gain_wide_band():
    assert rc._elevation_gain_hysteresis([100, 105, 103, 110], 8.0) == 10.0


# ---------------------------------------------------------------------------
# Route normalisation
# ---------------------------------------------------------------------------

def test_normalise_points_empty():
    assert rc._normalise_points([], []) == []


def test_normalise_points_north_up():
    points = rc._normalise_points([48.0, 48.01], [9.0, 9.0])
    assert points[0][1] > points[1][1]


def test_normalise_points_keeps_the_shape():
    # At the equator, 0.02 degrees of longitude is twice 0.01 degrees of latitude.
    points = rc._normalise_points([0.0, 0.01], [0.0, 0.02])
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(1.0)
    assert min(ys) == pytest.approx(0.25)
    assert max(ys) == pytest.approx(0.75)


def test_fit_semicircles_to_degrees():
    assert rc._fit_semicircles_to_degrees(0) == pytest.approx(0.0)
    assert rc._fit_semicircles_to_degrees(2**30) == pytest.approx(90.0)
    assert rc._fit_semicircles_to_degrees(2**31) == pytest.approx(180.0)
    assert rc._fit_semicircles_to_degrees(-2**31) == pytest.approx(-180.0)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0, "0:00"),
    (59, "0:59"),
    (60, "1:00"),
    (2242, "37:22"),
    (3600, "1:00:00"),
    (3723, "1:02:03"),
])
def test_fmt_duration(seconds, expected):
    assert rc.fmt_duration(seconds) == expected


def test_fmt_pace():
    assert rc.fmt_pace(2242, 10.28) == "3:38"
    assert rc.fmt_pace(100, 0) == "--:--"


@pytest.mark.parametrize("pace,expected", [
    (3.636, "3:38"),
    (3.999, "4:00"),
    (None, "--:--"),
    (0, "--:--"),
])
def test_fmt_pace_value(pace, expected):
    assert rc.fmt_pace_value(pace) == expected


def test_fmt_speed():
    assert rc.fmt_speed(2242, 10.28) == "16.5"
    assert rc.fmt_speed(0, 10.28) == "--"
    assert rc.fmt_speed(2242, 0) == "--"


@pytest.mark.parametrize("pace,expected", [
    (3.636, "16.5"),
    (None, "--"),
    (0, "--"),
])
def test_fmt_speed_value(pace, expected):
    assert rc.fmt_speed_value(pace) == expected


@pytest.mark.parametrize("text,expected", [
    ("1:02:03", 3723),
    ("37:22", 2242),
    ("90", 90),
])
def test_parse_time_input(text, expected):
    assert rc.parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1:2:3:4"])
def test_parse_time_input_rejects_bad_text(text):
    with pytest.raises(ValueError):
        rc.parse_time_input(text)


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------

def test_parse_gpx_demo(demo_gpx):
    total, distance, gain, norm, elevations = demo_gpx
    assert total == 3600
    assert distance == pytest.approx(12.0, abs=0.01)
    assert gain == pytest.approx(56.0, abs=0.5)
    assert len(norm) == 721
    assert len(elevations) == 721
    assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in norm)


def test_parse_fit_race():
    total, distance, gain, norm, elevations, pace = rc.parse_fit(str(RACE_FIT))
    assert total == 2242
    assert distance == pytest.approx(10.28, abs=0.01)
    assert gain == pytest.approx(56.0, abs=0.5)
    assert len(norm) == 2243
    assert len(elevations) == 2243
    assert pace == pytest.approx(3.638, abs=0.01)


def test_parse_fit_uses_the_gps_distance():
    _, distance, _, _, _, _ = rc.parse_fit(str(RACE_FIT), distance_source="gps")
    assert distance == pytest.approx(10.098, abs=0.01)


# ---------------------------------------------------------------------------
# Card output
# ---------------------------------------------------------------------------

def test_generate_card_vertical(tmp_path, demo_gpx):
    total, distance, gain, norm, elevations = demo_gpx
    out = tmp_path / "vertical.png"
    rc.generate_card(total, distance, gain, norm, elevations, width=400, output=str(out))
    with Image.open(out) as img:
        assert img.mode == "RGBA"
        assert img.width == 400
        assert img.height > 400
        assert img.getpixel((0, 0))[3] == 0


def test_generate_card_horizontal(tmp_path):
    out = tmp_path / "horizontal.png"
    rc.generate_card(
        2242, 10.28, 56.0,
        layout="h", width=800, height=400,
        metric="speed", pace_min_km=3.638,
        output=str(out),
    )
    with Image.open(out) as img:
        assert img.size == (800, 400)
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0


def test_generate_card_rejects_an_unknown_metric(tmp_path):
    with pytest.raises(ValueError):
        rc.generate_card(2242, 10.28, metric="bogus", output=str(tmp_path / "x.png"))


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def test_cli_reports_a_missing_file():
    result = subprocess.run(
        [sys.executable, str(ROOT / "running-card.py"), "missing.gpx"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "File not found" in result.stderr
