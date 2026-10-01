"""Tests des utilitaires numériques et de couleur."""

from __future__ import annotations

import pytest

import luminosite as lum


def test_clamp_inside_and_bounds() -> None:
    assert lum._clamp(0.5, 0.0, 1.0) == 0.5
    assert lum._clamp(-1.0, 0.0, 1.0) == 0.0
    assert lum._clamp(2.0, 0.0, 1.0) == 1.0


def test_hex_to_rgb() -> None:
    assert lum._hex_to_rgb("#ffffff") == (255, 255, 255)
    assert lum._hex_to_rgb("000000") == (0, 0, 0)
    assert lum._hex_to_rgb("#7dd3a0") == (0x7D, 0xD3, 0xA0)


def test_kelvin_to_rgb_daylight_near_white() -> None:
    r, g, b = lum.kelvin_to_rgb(6500)
    assert r == pytest.approx(1.0, abs=0.05)
    assert g == pytest.approx(1.0, abs=0.05)
    assert b == pytest.approx(1.0, abs=0.05)


def test_kelvin_to_rgb_warm_reduces_blue() -> None:
    r_warm, g_warm, b_warm = lum.kelvin_to_rgb(1500)
    r_day, g_day, b_day = lum.kelvin_to_rgb(6500)
    assert b_warm < b_day
    assert r_warm >= r_day * 0.9


def test_night_shift_to_kelvin_extremes() -> None:
    assert lum.night_shift_to_kelvin(0.0) == lum.NEUTRAL_KELVIN
    assert lum.night_shift_to_kelvin(1.0) == lum.WARM_KELVIN
    assert lum.night_shift_to_kelvin(0.5) == int(
        round(lum.NEUTRAL_KELVIN - 0.5 * (lum.NEUTRAL_KELVIN - lum.WARM_KELVIN))
    )


def test_night_shift_to_kelvin_clamps() -> None:
    assert lum.night_shift_to_kelvin(-1.0) == lum.NEUTRAL_KELVIN
    assert lum.night_shift_to_kelvin(2.0) == lum.WARM_KELVIN


def test_night_shift_to_gamma_off_is_neutral() -> None:
    gamma = lum.night_shift_to_gamma(0.0)
    assert all(channel == pytest.approx(1.0, abs=0.05) for channel in gamma)


def test_night_shift_to_gamma_warm_reduces_blue_channel() -> None:
    off = lum.night_shift_to_gamma(0.0)
    warm = lum.night_shift_to_gamma(1.0)
    assert warm[2] < off[2]
