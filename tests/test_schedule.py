"""Tests horaires et programmation Night Shift."""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path

import pytest

import luminosite as lum


def test_parse_hhmm_valid() -> None:
    assert lum.parse_hhmm("22:00") == time(22, 0)
    assert lum.parse_hhmm(" 7:05 ") == time(7, 5)
    assert lum.parse_hhmm("00:00") == time(0, 0)
    assert lum.parse_hhmm("23:59") == time(23, 59)


@pytest.mark.parametrize(
    "value",
    ["", "25:00", "12:60", "noon", "12", "12:0", "ab:cd"],
)
def test_parse_hhmm_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        lum.parse_hhmm(value)


def test_format_hhmm() -> None:
    assert lum.format_hhmm(time(7, 5)) == "07:05"
    assert lum.format_hhmm("9:30") == "09:30"


def test_is_within_schedule_same_day() -> None:
    start, end = time(9, 0), time(17, 0)
    assert lum.is_within_schedule(time(9, 0), start, end)
    assert lum.is_within_schedule(time(12, 0), start, end)
    assert not lum.is_within_schedule(time(17, 0), start, end)
    assert not lum.is_within_schedule(time(8, 59), start, end)


def test_is_within_schedule_overnight() -> None:
    start, end = time(22, 0), time(7, 0)
    assert lum.is_within_schedule(time(22, 0), start, end)
    assert lum.is_within_schedule(time(23, 30), start, end)
    assert lum.is_within_schedule(time(0, 0), start, end)
    assert lum.is_within_schedule(time(6, 59), start, end)
    assert not lum.is_within_schedule(time(7, 0), start, end)
    assert not lum.is_within_schedule(time(12, 0), start, end)


def test_is_within_schedule_full_day() -> None:
    t = time(12, 0)
    assert lum.is_within_schedule(t, time(8, 0), time(8, 0))


def test_schedule_duration_hours() -> None:
    assert lum.schedule_duration_hours("22:00", "07:00") == 9.0
    assert lum.schedule_duration_hours("09:00", "17:00") == 8.0
    assert lum.schedule_duration_hours("08:00", "08:00") == 24.0


def test_minutes_roundtrip() -> None:
    assert lum._hhmm_from_minutes(lum._minutes_from_hhmm("22:30")) == "22:30"
    assert lum._hhmm_from_minutes(25 * 60 + 5) == "01:05"


def test_desired_night_disabled(schedule_enabled: dict[str, object]) -> None:
    schedule_enabled["enabled"] = False
    assert lum.desired_night_from_schedule(schedule_enabled, datetime(2026, 1, 1, 23, 0)) is None


def test_desired_night_inside_window(schedule_enabled: dict[str, object]) -> None:
    assert (
        lum.desired_night_from_schedule(schedule_enabled, datetime(2026, 1, 1, 23, 0))
        == 0.60
    )


def test_desired_night_outside_window(schedule_enabled: dict[str, object]) -> None:
    assert (
        lum.desired_night_from_schedule(schedule_enabled, datetime(2026, 1, 1, 12, 0))
        == 0.0
    )


def test_load_and_save_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    schedule_path = config_dir / "schedule.json"
    monkeypatch.setattr(lum, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(lum, "SCHEDULE_PATH", schedule_path)

    default = lum.load_schedule()
    assert default["enabled"] is False
    assert default["start"] == "22:00"

    saved = lum.save_schedule(
        {"enabled": True, "start": "21:30", "end": "6:15", "intensity": 0.8}
    )
    assert saved == {
        "enabled": True,
        "start": "21:30",
        "end": "06:15",
        "intensity": 0.8,
    }
    assert json.loads(schedule_path.read_text(encoding="utf-8")) == saved

    loaded = lum.load_schedule()
    assert loaded == saved


def test_load_schedule_corrupt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    schedule_path = config_dir / "schedule.json"
    config_dir.mkdir()
    schedule_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(lum, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(lum, "SCHEDULE_PATH", schedule_path)

    loaded = lum.load_schedule()
    assert loaded["enabled"] is False
    assert loaded["start"] == lum.DEFAULT_SCHEDULE["start"]
