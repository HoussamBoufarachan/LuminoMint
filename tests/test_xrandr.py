"""Tests détection xrandr et lecture luminosité (subprocess mocké)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import luminosite as lum


def _completed(stdout: str, returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def test_detect_output_prefers_primary(
    monkeypatch: pytest.MonkeyPatch, xrandr_query_primary: str
) -> None:
    monkeypatch.setattr(
        lum.subprocess,
        "run",
        lambda *a, **k: _completed(xrandr_query_primary),
    )
    assert lum.detect_output() == "eDP-1"


def test_detect_output_first_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = "HDMI-1 connected\nDP-1 disconnected\n"
    monkeypatch.setattr(
        lum.subprocess,
        "run",
        lambda *a, **k: _completed(stdout),
    )
    assert lum.detect_output() == "HDMI-1"


def test_detect_output_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        lum.subprocess,
        "run",
        lambda *a, **k: _completed("DP-1 disconnected\n"),
    )
    with pytest.raises(RuntimeError, match="Aucun écran"):
        lum.detect_output()


def test_get_brightness_for_output(
    monkeypatch: pytest.MonkeyPatch, xrandr_verbose_sample: str
) -> None:
    monkeypatch.setattr(
        lum.subprocess,
        "run",
        lambda *a, **k: _completed(xrandr_verbose_sample),
    )
    assert lum.get_brightness("eDP-1") == 0.75
    assert lum.get_brightness("HDMI-1") == 1.0


def test_get_gamma_for_output(
    monkeypatch: pytest.MonkeyPatch, xrandr_verbose_sample: str
) -> None:
    monkeypatch.setattr(
        lum.subprocess,
        "run",
        lambda *a, **k: _completed(xrandr_verbose_sample),
    )
    assert lum.get_gamma("eDP-1") == (1.0, 1.0, 1.0)
    gamma = lum.get_gamma("HDMI-1")
    assert gamma[0] == pytest.approx(1.0 / 1.2)
    assert gamma[1] == pytest.approx(1.0 / 1.1)
    assert gamma[2] == pytest.approx(1.0)


def test_require_xrandr_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lum.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="xrandr"):
        lum.require_xrandr()


def test_set_display_clamps_and_calls_xrandr(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):  # noqa: ANN001
        calls.append(list(cmd))
        return _completed("")

    monkeypatch.setattr(lum.subprocess, "run", fake_run)
    brightness, night = lum.set_display("eDP-1", 2.0, -0.5)
    assert brightness == lum.MAX_BRIGHTNESS
    assert night == lum.MIN_NIGHT_SHIFT
    assert calls[0][0] == "xrandr"
    assert "--output" in calls[0]
    assert "eDP-1" in calls[0]
    assert "--brightness" in calls[0]
    assert "--gamma" in calls[0]


def test_run_cli_no_args_returns_false() -> None:
    assert lum.run_cli([]) is False


def test_run_cli_status(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        lum,
        "snapshot",
        lambda output=None: {
            "output": "eDP-1",
            "brightness": 0.8,
            "night_shift": 0.0,
            "kelvin": 6500,
            "brightness_label": "80 %",
            "night_label": "Off",
        },
    )
    monkeypatch.setattr(
        lum,
        "load_schedule",
        lambda: dict(lum.DEFAULT_SCHEDULE),
    )
    assert lum.run_cli(["--status"]) is True
    out = capsys.readouterr().out
    assert '"brightness": 0.8' in out
    assert '"output": "eDP-1"' in out
