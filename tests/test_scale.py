"""Tests mapping slider AccentScale (logique pure)."""

from __future__ import annotations

import pytest

import luminosite as lum


def test_map_scale_value_edges() -> None:
    assert lum.map_scale_value(10, 100, 0.0, 1.0, pad=10.0) == pytest.approx(0.0)
    assert lum.map_scale_value(90, 100, 0.0, 1.0, pad=10.0) == pytest.approx(1.0)


def test_map_scale_value_midpoint() -> None:
    assert lum.map_scale_value(50, 100, 0.0, 1.0, pad=10.0) == pytest.approx(0.5)


def test_map_scale_value_clamps() -> None:
    assert lum.map_scale_value(-20, 100, 0.05, 1.05, pad=10.0) == pytest.approx(0.05)
    assert lum.map_scale_value(999, 100, 0.05, 1.05, pad=10.0) == pytest.approx(1.05)


def test_map_scale_value_range() -> None:
    value = lum.map_scale_value(50, 100, 0.05, 1.05, pad=10.0)
    assert value == pytest.approx(0.55)
