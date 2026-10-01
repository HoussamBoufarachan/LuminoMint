"""Tests parsing gamma et conversion Night Shift."""

from __future__ import annotations

import pytest

import luminosite as lum


def test_parse_gamma_direct() -> None:
    assert lum._parse_gamma("\tGamma: 1.000:0.900:0.800") == (1.0, 0.9, 0.8)


def test_parse_gamma_inverted_from_verbose() -> None:
    # xrandr --verbose affiche parfois l'inverse (> 1.01)
    parsed = lum._parse_gamma("\tGamma: 1.5:1.25:2.0")
    assert parsed is not None
    assert parsed[0] == pytest.approx(1.0 / 1.5)
    assert parsed[1] == pytest.approx(1.0 / 1.25)
    assert parsed[2] == pytest.approx(1.0 / 2.0)


def test_parse_gamma_missing() -> None:
    assert lum._parse_gamma("Brightness: 0.5") is None


def test_gamma_to_night_shift_neutral() -> None:
    assert lum.gamma_to_night_shift((1.0, 1.0, 1.0)) == 0.0
    assert lum.gamma_to_night_shift((1.0, 1.0, 0.99)) == 0.0


def test_gamma_to_night_shift_warm() -> None:
    warm_gamma = lum.night_shift_to_gamma(1.0)
    intensity = lum.gamma_to_night_shift(warm_gamma)
    assert intensity == pytest.approx(1.0, abs=0.05)


def test_next_compact_brightness_cycle() -> None:
    assert lum.next_compact_brightness(0.25) == 0.50
    assert lum.next_compact_brightness(0.50) == 1.00
    assert lum.next_compact_brightness(1.00) == 0.25


def test_next_compact_brightness_snap_up() -> None:
    assert lum.next_compact_brightness(0.10) == 0.25
    assert lum.next_compact_brightness(0.40) == 0.50
    assert lum.next_compact_brightness(0.80) == 1.00
