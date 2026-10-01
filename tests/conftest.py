"""Fixtures partagées pour les tests luminosité."""

from __future__ import annotations

import pytest


@pytest.fixture
def schedule_enabled() -> dict[str, object]:
    return {
        "enabled": True,
        "start": "22:00",
        "end": "07:00",
        "intensity": 0.60,
    }


@pytest.fixture
def xrandr_query_primary() -> str:
    return (
        "Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767\n"
        "eDP-1 connected primary 1920x1080+0+0\n"
        "HDMI-1 connected 1920x1080+1920+0\n"
        "DP-1 disconnected\n"
    )


@pytest.fixture
def xrandr_verbose_sample() -> str:
    return (
        "eDP-1 connected primary 1920x1080+0+0\n"
        "\tBrightness: 0.75\n"
        "\tGamma: 1.0:1.0:1.0\n"
        "HDMI-1 connected 1920x1080+1920+0\n"
        "\tBrightness: 1.00\n"
        "\tGamma: 1.2:1.1:1.0\n"
    )
