#!/usr/bin/env python3
"""LuminoMint — contrôle de luminosité écran via xrandr."""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import datetime, time
from pathlib import Path
from tkinter import ttk, messagebox

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]

MIN_BRIGHTNESS = 0.05
MAX_BRIGHTNESS = 1.05
STEP = 0.05

MIN_NIGHT_SHIFT = 0.0
MAX_NIGHT_SHIFT = 1.0
NIGHT_SHIFT_STEP = 0.05
# 6500 K = lumière du jour ; 1500 K = ambre (filtre anti-bleu max)
NEUTRAL_KELVIN = 6500
WARM_KELVIN = 1500

COMPACT_BRIGHTNESS_STEPS = (0.25, 0.50, 1.00)
COMPACT_NIGHT_SHIFT = 0.60
PROJECT_DIR = Path(__file__).resolve().parent
ICON_DIR = PROJECT_DIR / "icons"
ICON_SIZE = 28
APPLET_UUID = "luminosite@luminosite"
APPLET_SRC = PROJECT_DIR / APPLET_UUID
APPLET_INSTALL = Path.home() / ".local/share/cinnamon/applets" / APPLET_UUID
RELOAD_APPLET_SH = PROJECT_DIR / "reload-applet.sh"
CONFIG_DIR = Path.home() / ".config" / "luminosite"
SCHEDULE_PATH = CONFIG_DIR / "schedule.json"
DEFAULT_SCHEDULE = {
    "enabled": False,
    "start": "22:00",
    "end": "07:00",
    "intensity": COMPACT_NIGHT_SHIFT,
}
# Remix Icon — https://remixicon.com
ICON_SUN_LINE = "sun-line"
ICON_SUN_FILL = "sun-fill"
ICON_MOON_LINE = "moon-clear-line"
ICON_MOON_FILL = "moon-clear-fill"
ICON_EXPAND = "fullscreen-line"
ICON_COMPACT = "picture-in-picture-2-line"
ICON_ADD = "add-line"
ICON_SUBTRACT = "subtract-line"
ICON_REFRESH = "refresh-line"
ICON_COMPUTER = "computer-line"
ICON_CLOSE = "close-line"

BG = "#16181d"
CARD = "#22262e"
BTN = "#2d323c"
BTN_HOVER = "#3a404c"
TEXT = "#e8eaed"
MUTED = "#8b919a"
GREEN = "#7dd3a0"
GREEN_DIM = "#4e8f68"
GREEN_BRIGHT = "#c8f5d8"
AMBER = "#f0b060"
UI_FONT = "DejaVu Sans"


def require_xrandr() -> None:
    if shutil.which("xrandr") is None:
        raise RuntimeError("xrandr introuvable. Installez le paquet x11-xserver-utils.")


def detect_output() -> str:
    """Détecte la sortie primaire, sinon le premier écran connecté."""
    result = subprocess.run(
        ["xrandr", "--query"],
        check=True,
        capture_output=True,
        text=True,
    )
    primary = None
    connected = None
    for line in result.stdout.splitlines():
        if " connected" not in line:
            continue
        name = line.split()[0]
        if connected is None:
            connected = name
        if " primary" in line:
            primary = name
            break
    output = primary or connected
    if not output:
        raise RuntimeError("Aucun écran connecté détecté.")
    return output


def get_brightness(output: str) -> float:
    result = subprocess.run(
        ["xrandr", "--verbose"],
        check=True,
        capture_output=True,
        text=True,
    )
    current_output = None
    for line in result.stdout.splitlines():
        if " connected" in line or " disconnected" in line:
            current_output = line.split()[0]
            continue
        if current_output == output:
            match = re.search(r"Brightness:\s*([0-9.]+)", line)
            if match:
                return float(match.group(1))
    # Fallback : première valeur Brightness trouvée
    match = re.search(r"Brightness:\s*([0-9.]+)", result.stdout)
    if match:
        return float(match.group(1))
    return 1.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def load_remix_icon(name: str, color: str, size: int = ICON_SIZE) -> tk.PhotoImage:
    """Charge une icône Remix Icon (PNG) et la teinte."""
    path = ICON_DIR / f"{name}.png"
    if not path.is_file():
        raise FileNotFoundError(f"Icône Remix Icon introuvable : {path}")
    if Image is not None and ImageTk is not None:
        img = Image.open(path).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.Resampling.LANCZOS)
        red, green, blue = _hex_to_rgb(color)
        tinted = []
        for _r, _g, _b, alpha in img.getdata():
            tinted.append((red, green, blue, alpha) if alpha else (0, 0, 0, 0))
        img.putdata(tinted)
        return ImageTk.PhotoImage(img)
    return tk.PhotoImage(file=str(path))


def kelvin_to_rgb(temp_k: float) -> tuple[float, float, float]:
    """Approximation RGB d'une température de couleur (algorithme Tanner Helland)."""
    temp = temp_k / 100.0
    if temp <= 66:
        red = 255.0
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
    if temp >= 66:
        blue = 255.0
    elif temp <= 19:
        blue = 0.0
    else:
        blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307
    return (
        _clamp(red, 0.0, 255.0) / 255.0,
        _clamp(green, 0.0, 255.0) / 255.0,
        _clamp(blue, 0.0, 255.0) / 255.0,
    )


_NEUTRAL_RGB = kelvin_to_rgb(NEUTRAL_KELVIN)


def night_shift_to_kelvin(intensity: float) -> int:
    intensity = _clamp(intensity, MIN_NIGHT_SHIFT, MAX_NIGHT_SHIFT)
    kelvin = NEUTRAL_KELVIN - intensity * (NEUTRAL_KELVIN - WARM_KELVIN)
    return int(round(kelvin))


def night_shift_to_gamma(intensity: float) -> tuple[float, float, float]:
    """Convertit l'intensité Night Shift (0–1) en gamma R:G:B xrandr."""
    red, green, blue = kelvin_to_rgb(night_shift_to_kelvin(intensity))
    nr, ng, nb = _NEUTRAL_RGB
    return (
        _clamp(red / nr, 0.10, 1.0),
        _clamp(green / ng, 0.10, 1.0),
        _clamp(blue / nb, 0.10, 1.0),
    )


def _parse_gamma(raw: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"Gamma:\s*([0-9.]+)\s*:\s*([0-9.]+)\s*:\s*([0-9.]+)",
        raw,
    )
    if not match:
        return None
    red, green, blue = (float(match.group(i)) for i in (1, 2, 3))
    # xrandr --verbose affiche l'inverse des valeurs passées à --gamma
    if red > 1.01 or green > 1.01 or blue > 1.01:
        red, green, blue = (
            1.0 / red if red else 1.0,
            1.0 / green if green else 1.0,
            1.0 / blue if blue else 1.0,
        )
    return red, green, blue


def gamma_to_night_shift(gamma: tuple[float, float, float]) -> float:
    """Estime l'intensité Night Shift à partir du canal bleu (le plus sensible)."""
    _warm_r, _warm_g, warm_b = night_shift_to_gamma(MAX_NIGHT_SHIFT)
    blue = _clamp(gamma[2], warm_b, 1.0)
    if blue >= 0.98:
        return 0.0
    span = 1.0 - warm_b
    if span <= 0:
        return 0.0
    return _clamp(round((1.0 - blue) / span, 2), MIN_NIGHT_SHIFT, MAX_NIGHT_SHIFT)


def get_gamma(output: str) -> tuple[float, float, float]:
    result = subprocess.run(
        ["xrandr", "--verbose"],
        check=True,
        capture_output=True,
        text=True,
    )
    current_output = None
    pending: tuple[float, float, float] | None = None
    for line in result.stdout.splitlines():
        if " connected" in line or " disconnected" in line:
            current_output = line.split()[0]
            continue
        if current_output != output:
            continue
        parsed = _parse_gamma(line)
        if parsed:
            pending = parsed
            break
    if pending:
        return pending
    parsed = _parse_gamma(result.stdout)
    return parsed if parsed else (1.0, 1.0, 1.0)


def set_display(
    output: str,
    brightness: float,
    night_shift: float,
) -> tuple[float, float]:
    brightness = _clamp(round(brightness, 2), MIN_BRIGHTNESS, MAX_BRIGHTNESS)
    night_shift = _clamp(round(night_shift, 2), MIN_NIGHT_SHIFT, MAX_NIGHT_SHIFT)
    red, green, blue = night_shift_to_gamma(night_shift)
    subprocess.run(
        [
            "xrandr",
            "--output",
            output,
            "--brightness",
            f"{brightness:.2f}",
            "--gamma",
            f"{red:.3f}:{green:.3f}:{blue:.3f}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return brightness, night_shift


def next_compact_brightness(current: float) -> float:
    next_value = COMPACT_BRIGHTNESS_STEPS[0]
    for index, step in enumerate(COMPACT_BRIGHTNESS_STEPS):
        if abs(current - step) < 0.03:
            return COMPACT_BRIGHTNESS_STEPS[
                (index + 1) % len(COMPACT_BRIGHTNESS_STEPS)
            ]
        if current < step - 0.01:
            return step
    return next_value


def snapshot(output: str | None = None) -> dict[str, object]:
    require_xrandr()
    output = output or detect_output()
    brightness = get_brightness(output)
    night_shift = gamma_to_night_shift(get_gamma(output))
    return {
        "output": output,
        "brightness": round(brightness, 2),
        "night_shift": round(night_shift, 2),
        "kelvin": night_shift_to_kelvin(night_shift),
        "brightness_label": f"{int(round(brightness * 100))} %",
        "night_label": (
            "Off" if night_shift <= 0.005 else f"{int(round(night_shift * 100))} %"
        ),
    }


def parse_hhmm(value: str) -> time:
    match = re.fullmatch(r"\s*(\d{1,2})\s*:\s*(\d{2})\s*", value or "")
    if not match:
        raise ValueError(f"Heure invalide : {value!r} (attendu HH:MM)")
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Heure hors plage : {value!r}")
    return time(hour, minute)


def format_hhmm(value: time | str) -> str:
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"
    return format_hhmm(parse_hhmm(value))


def load_schedule() -> dict[str, object]:
    data = dict(DEFAULT_SCHEDULE)
    if SCHEDULE_PATH.is_file():
        try:
            loaded = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    data["enabled"] = bool(data.get("enabled", False))
    data["start"] = format_hhmm(str(data.get("start", DEFAULT_SCHEDULE["start"])))
    data["end"] = format_hhmm(str(data.get("end", DEFAULT_SCHEDULE["end"])))
    data["intensity"] = _clamp(
        float(data.get("intensity", COMPACT_NIGHT_SHIFT)),
        MIN_NIGHT_SHIFT,
        MAX_NIGHT_SHIFT,
    )
    return data


def save_schedule(schedule: dict[str, object]) -> dict[str, object]:
    cleaned = {
        "enabled": bool(schedule.get("enabled", False)),
        "start": format_hhmm(str(schedule.get("start", DEFAULT_SCHEDULE["start"]))),
        "end": format_hhmm(str(schedule.get("end", DEFAULT_SCHEDULE["end"]))),
        "intensity": round(
            _clamp(
                float(schedule.get("intensity", COMPACT_NIGHT_SHIFT)),
                MIN_NIGHT_SHIFT,
                MAX_NIGHT_SHIFT,
            ),
            2,
        ),
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cleaned


def is_within_schedule(now: time, start: time, end: time) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def desired_night_from_schedule(
    schedule: dict[str, object] | None = None,
    now: datetime | None = None,
) -> float | None:
    """Retourne l'intensité Night Shift voulue, ou None si pas de programmation."""
    schedule = schedule or load_schedule()
    if not schedule.get("enabled"):
        return None
    now_t = (now or datetime.now()).time().replace(second=0, microsecond=0)
    start = parse_hhmm(str(schedule["start"]))
    end = parse_hhmm(str(schedule["end"]))
    if is_within_schedule(now_t, start, end):
        return float(schedule["intensity"])
    return 0.0


def apply_schedule(output: str | None = None) -> dict[str, object]:
    """Applique le Night Shift selon la programmation, sans toucher sinon."""
    data = snapshot(output)
    desired = desired_night_from_schedule()
    if desired is None:
        data["schedule"] = load_schedule()
        data["schedule_active"] = False
        return data
    current_night = float(data["night_shift"])
    if abs(current_night - desired) >= 0.02:
        brightness = float(data["brightness"])
        set_display(str(data["output"]), brightness, desired)
        data = snapshot(str(data["output"]))
    data["schedule"] = load_schedule()
    data["schedule_active"] = True
    data["schedule_desired"] = desired
    return data


def run_cli(argv: list[str] | None = None) -> bool:
    """Exécute une action sans interface. Retourne False s'il faut lancer la fenêtre."""
    parser = argparse.ArgumentParser(
        prog="luminomint",
        description="LuminoMint — contrôle de luminosité écran via xrandr.",
    )
    parser.add_argument("--status", action="store_true", help="Affiche l'état JSON")
    parser.add_argument(
        "--cycle-brightness",
        action="store_true",
        help="Alterne 25 % / 50 % / 100 %",
    )
    parser.add_argument(
        "--toggle-night",
        action="store_true",
        help="Active ou désactive le Night Shift",
    )
    parser.add_argument(
        "--adjust-brightness",
        type=float,
        metavar="DELTA",
        help="Ajuste la luminosité (ex. 0.05 ou -0.05)",
    )
    parser.add_argument(
        "--adjust-night",
        type=float,
        metavar="DELTA",
        help="Ajuste le Night Shift (ex. 0.05 ou -0.05)",
    )
    parser.add_argument(
        "--set-brightness",
        type=float,
        metavar="VALUE",
        help="Fixe la luminosité (ex. 0.75)",
    )
    parser.add_argument(
        "--set-night",
        type=float,
        metavar="VALUE",
        help="Fixe le Night Shift (ex. 0.60)",
    )
    parser.add_argument(
        "--apply-schedule",
        action="store_true",
        help="Applique la programmation Night Shift",
    )
    args = parser.parse_args(argv)
    cli_requested = any(
        (
            args.status,
            args.cycle_brightness,
            args.toggle_night,
            args.adjust_brightness is not None,
            args.adjust_night is not None,
            args.set_brightness is not None,
            args.set_night is not None,
            args.apply_schedule,
        )
    )
    if not cli_requested:
        return False

    if args.apply_schedule:
        data = apply_schedule()
        json.dump(data, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return True

    data = snapshot()
    output = str(data["output"])
    brightness = float(data["brightness"])
    night_shift = float(data["night_shift"])

    if not args.status:
        if args.cycle_brightness:
            brightness = next_compact_brightness(brightness)
        if args.toggle_night:
            night_shift = 0.0 if night_shift > 0.005 else COMPACT_NIGHT_SHIFT
        if args.adjust_brightness is not None:
            brightness += args.adjust_brightness
        if args.adjust_night is not None:
            night_shift += args.adjust_night
        if args.set_brightness is not None:
            brightness = args.set_brightness
        if args.set_night is not None:
            night_shift = args.set_night
        brightness, night_shift = set_display(output, brightness, night_shift)
        data = snapshot(output)

    data["schedule"] = load_schedule()
    json.dump(data, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return True


def _gsettings_get(schema: str, key: str) -> str:
    return subprocess.check_output(
        ["gsettings", "get", schema, key],
        text=True,
    ).strip()


def _gsettings_set(schema: str, key: str, value: str) -> None:
    subprocess.run(["gsettings", "set", schema, key, value], check=True)


def _gsettings_list(items: list[str]) -> str:
    return "[" + ", ".join("'" + item.replace("'", r"\'") + "'" for item in items) + "]"


def ensure_applet_symlink() -> None:
    if not APPLET_SRC.is_dir():
        return
    APPLET_INSTALL.parent.mkdir(parents=True, exist_ok=True)
    target = APPLET_SRC.resolve()
    if APPLET_INSTALL.exists() or APPLET_INSTALL.is_symlink():
        try:
            if APPLET_INSTALL.resolve() == target:
                return
        except OSError:
            pass
        APPLET_INSTALL.unlink()
    APPLET_INSTALL.symlink_to(target)


def ensure_panel_applet() -> None:
    """Installe l'applet et l'ajoute au panneau Cinnamon si elle n'y est pas."""
    try:
        ensure_applet_symlink()
        raw = _gsettings_get("org.cinnamon", "enabled-applets")
        applets: list[str] = list(ast.literal_eval(raw))
        if any(APPLET_UUID in item for item in applets):
            return
        next_id = int(_gsettings_get("org.cinnamon", "next-applet-id"))
        updated: list[str] = []
        inserted = False
        sound_pos = 0
        for item in applets:
            panel, zone, pos, rest = item.split(":", 3)
            if (
                not inserted
                and panel == "panel1"
                and zone == "right"
                and rest.startswith("sound@cinnamon.org")
            ):
                sound_pos = int(pos)
                updated.append(f"panel1:right:{sound_pos}:{APPLET_UUID}:{next_id}")
                inserted = True
            if (
                inserted
                and panel == "panel1"
                and zone == "right"
                and int(pos) >= sound_pos
            ):
                updated.append(f"{panel}:{zone}:{int(pos) + 1}:{rest}")
            else:
                updated.append(item)
        if not inserted:
            right_pos = [
                int(item.split(":")[2])
                for item in applets
                if item.startswith("panel1:right:")
            ]
            pos = (max(right_pos) + 1) if right_pos else 0
            updated.append(f"panel1:right:{pos}:{APPLET_UUID}:{next_id}")
        _gsettings_set("org.cinnamon", "enabled-applets", _gsettings_list(updated))
        _gsettings_set("org.cinnamon", "next-applet-id", str(next_id + 1))
    except Exception:  # noqa: BLE001
        return


def reload_applet() -> None:
    """Recharge l'applet Cinnamon (équivalent à reload-applet.sh)."""
    try:
        if RELOAD_APPLET_SH.is_file():
            subprocess.run(
                ["bash", str(RELOAD_APPLET_SH)],
                check=False,
                capture_output=True,
                text=True,
            )
            return
        subprocess.run(
            [
                "dbus-send",
                "--session",
                "--type=method_call",
                "--dest=org.Cinnamon",
                "/org/Cinnamon",
                "org.Cinnamon.ReloadXlet",
                f"string:{APPLET_UUID}",
                "string:APPLET",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return


def set_brightness(output: str, value: float) -> float:
    value = _clamp(round(value, 2), MIN_BRIGHTNESS, MAX_BRIGHTNESS)
    subprocess.run(
        ["xrandr", "--output", output, "--brightness", f"{value:.2f}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return value


def _minutes_from_hhmm(value: str) -> int:
    parsed = parse_hhmm(value)
    return parsed.hour * 60 + parsed.minute


def _hhmm_from_minutes(total: int) -> str:
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def schedule_duration_hours(start: str, end: str) -> float:
    start_m = _minutes_from_hhmm(start)
    end_m = _minutes_from_hhmm(end)
    span = (end_m - start_m) % (24 * 60)
    if span == 0:
        span = 24 * 60
    return span / 60.0


class ScheduleWheel(tk.Frame):
    """Roue 24 h — réglage uniquement via les poignées aux extrémités."""

    SIZE = 280
    RING = 22
    HANDLE = 18
    SNAP = 5  # minutes
    TRACK = "#1a1d24"
    TRACK_EDGE = "#2e3440"
    TICK = "#4a5160"
    TICK_MAJOR = "#8b919a"

    def __init__(
        self,
        parent: tk.Misc,
        start_var: tk.StringVar,
        end_var: tk.StringVar,
        on_change=None,
        **kwargs,
    ) -> None:
        super().__init__(parent, bg=CARD, **kwargs)
        self.start_var = start_var
        self.end_var = end_var
        self.on_change = on_change
        self._drag: str | None = None
        self._arc_origin_angle = 0.0
        self._arc_start_minutes = 0
        self._arc_end_minutes = 0
        self._suppress = False

        header = tk.Frame(self, bg=CARD)
        header.pack(fill="x", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)

        left = tk.Frame(header, bg=CARD)
        left.grid(row=0, column=0, sticky="w")
        tk.Label(
            left, text="☾  Coucher", bg=CARD, fg=AMBER, font=(UI_FONT, 9, "bold")
        ).pack(anchor="w")
        self.start_lbl = tk.Label(
            left, text="22:00", bg=CARD, fg=TEXT, font=(UI_FONT, 22, "bold")
        )
        self.start_lbl.pack(anchor="w")

        right = tk.Frame(header, bg=CARD)
        right.grid(row=0, column=1, sticky="e")
        tk.Label(
            right, text="Réveil  ☀", bg=CARD, fg=GREEN, font=(UI_FONT, 9, "bold")
        ).pack(anchor="e")
        self.end_lbl = tk.Label(
            right, text="07:00", bg=CARD, fg=TEXT, font=(UI_FONT, 22, "bold")
        )
        self.end_lbl.pack(anchor="e")

        self.canvas = tk.Canvas(
            self,
            width=self.SIZE,
            height=self.SIZE,
            bg=CARD,
            highlightthickness=0,
            bd=0,
            cursor="arrow",
        )
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        self.start_var.trace_add("write", lambda *_: self._on_var_write())
        self.end_var.trace_add("write", lambda *_: self._on_var_write())
        self.redraw()

    def _on_var_write(self) -> None:
        if self._suppress or self._drag:
            return
        self.redraw()

    def set_times(self, start: str, end: str) -> None:
        self._suppress = True
        self.start_var.set(format_hhmm(start))
        self.end_var.set(format_hhmm(end))
        self._suppress = False
        self.redraw()

    def _center(self) -> tuple[float, float]:
        return self.SIZE / 2, self.SIZE / 2

    def _radius(self) -> float:
        return self.SIZE / 2 - self.HANDLE - 10

    def _minutes_to_angle(self, minutes: int) -> float:
        return (minutes % (24 * 60)) / (24 * 60) * 360.0

    def _angle_to_minutes(self, angle: float) -> int:
        angle %= 360.0
        raw = int(round(angle / 360.0 * 24 * 60 / self.SNAP)) * self.SNAP
        return raw % (24 * 60)

    def _point(self, angle_deg: float, radius: float | None = None) -> tuple[float, float]:
        cx, cy = self._center()
        r = self._radius() if radius is None else radius
        rad = math.radians(angle_deg - 90)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    def _event_angle(self, event: tk.Event) -> float:
        cx, cy = self._center()
        return (math.degrees(math.atan2(event.y - cy, event.x - cx)) + 90) % 360

    def _handle_pos(self, which: str) -> tuple[float, float]:
        minutes = _minutes_from_hhmm(
            self.start_var.get() if which == "start" else self.end_var.get()
        )
        return self._point(self._minutes_to_angle(minutes))

    def _hit_handle(self, x: float, y: float) -> str | None:
        """Uniquement les extrémités (poignées)."""
        best: str | None = None
        best_d = self.HANDLE + 6
        for which in ("start", "end"):
            hx, hy = self._handle_pos(which)
            dist = math.hypot(x - hx, y - hy)
            if dist <= best_d:
                best_d = dist
                best = which
        return best

    def _span_minutes(self) -> tuple[int, int, int]:
        try:
            start_m = _minutes_from_hhmm(self.start_var.get())
            end_m = _minutes_from_hhmm(self.end_var.get())
        except ValueError:
            start_m, end_m = 22 * 60, 7 * 60
        span = (end_m - start_m) % (24 * 60)
        if span == 0:
            span = 24 * 60
        return start_m, end_m, span

    def _angle_on_arc(self, angle: float, start_a: float, extent: float) -> bool:
        rel = (angle - start_a) % 360.0
        return rel <= extent + 0.5

    def _hit_arc(self, x: float, y: float) -> bool:
        """True si le point est sur l'arc ambre (hors poignées)."""
        if self._hit_handle(x, y):
            return False
        cx, cy = self._center()
        dist = math.hypot(x - cx, y - cy)
        r = self._radius()
        if abs(dist - r) > self.RING / 2 + 4:
            return False
        start_m, end_m, _span = self._span_minutes()
        start_a = self._minutes_to_angle(start_m)
        end_a = self._minutes_to_angle(end_m)
        extent = (end_a - start_a) % 360.0
        if extent == 0:
            extent = 360.0
        return self._angle_on_arc(self._event_angle_xy(x, y), start_a, extent)

    def _event_angle_xy(self, x: float, y: float) -> float:
        cx, cy = self._center()
        return (math.degrees(math.atan2(y - cy, x - cx)) + 90) % 360

    def _on_hover(self, event: tk.Event) -> None:
        if self._drag == "arc":
            self.canvas.configure(cursor="fleur")
            return
        if self._drag:
            self.canvas.configure(cursor="hand2")
            return
        if self._hit_handle(event.x, event.y):
            self.canvas.configure(cursor="hand2")
        elif self._hit_arc(event.x, event.y):
            self.canvas.configure(cursor="fleur")
        else:
            self.canvas.configure(cursor="arrow")

    def _on_press(self, event: tk.Event) -> str:
        hit = self._hit_handle(event.x, event.y)
        if hit is not None:
            self._drag = hit
            self.canvas.configure(cursor="hand2")
            self._apply_angle(hit, self._event_angle(event))
            return "break"

        if self._hit_arc(event.x, event.y):
            start_m, end_m, _span = self._span_minutes()
            self._drag = "arc"
            self._arc_origin_angle = self._event_angle(event)
            self._arc_start_minutes = start_m
            self._arc_end_minutes = end_m
            self.canvas.configure(cursor="fleur")
            return "break"

        return "break"

    def _on_motion(self, event: tk.Event) -> str:
        if not self._drag:
            return "break"
        if self._drag == "arc":
            self._apply_arc_shift(self._event_angle(event))
        else:
            self._apply_angle(self._drag, self._event_angle(event))
        return "break"

    def _on_release(self, _event: tk.Event) -> str:
        self._drag = None
        if self.on_change:
            self.on_change()
        return "break"

    def _apply_arc_shift(self, angle: float) -> None:
        """Décale début et fin ensemble : la durée reste identique."""
        delta_angle = (angle - self._arc_origin_angle) % 360.0
        if delta_angle > 180:
            delta_angle -= 360.0
        delta_minutes = int(round(delta_angle / 360.0 * 24 * 60 / self.SNAP)) * self.SNAP
        start = (self._arc_start_minutes + delta_minutes) % (24 * 60)
        end = (self._arc_end_minutes + delta_minutes) % (24 * 60)
        self._suppress = True
        self.start_var.set(_hhmm_from_minutes(start))
        self.end_var.set(_hhmm_from_minutes(end))
        self._suppress = False
        self.redraw()
        if self.on_change:
            self.on_change()

    def _apply_angle(self, which: str, angle: float) -> None:
        value = _hhmm_from_minutes(self._angle_to_minutes(angle))
        self._suppress = True
        if which == "start":
            self.start_var.set(value)
        else:
            self.end_var.set(value)
        self._suppress = False
        self.redraw()
        if self.on_change:
            self.on_change()

    def redraw(self) -> None:
        self.canvas.delete("all")
        cx, cy = self._center()
        r = self._radius()
        track = r

        try:
            start_m = _minutes_from_hhmm(self.start_var.get())
            end_m = _minutes_from_hhmm(self.end_var.get())
        except ValueError:
            start_m, end_m = 22 * 60, 7 * 60

        start_a = self._minutes_to_angle(start_m)
        end_a = self._minutes_to_angle(end_m)
        extent = (end_a - start_a) % 360
        if extent == 0:
            extent = 360

        # Disque intérieur
        inner = r - self.RING / 2 - 6
        self.canvas.create_oval(
            cx - inner,
            cy - inner,
            cx + inner,
            cy + inner,
            fill="#12141a",
            outline="#252a33",
            width=1,
        )

        # Anneau de fond (double trait pour du relief)
        self.canvas.create_oval(
            cx - track - 1,
            cy - track - 1,
            cx + track + 1,
            cy + track + 1,
            outline=self.TRACK_EDGE,
            width=self.RING + 4,
        )
        self.canvas.create_oval(
            cx - track,
            cy - track,
            cx + track,
            cy + track,
            outline=self.TRACK,
            width=self.RING,
        )

        # Arc durée ambre
        tk_start = (90 - start_a) % 360
        self.canvas.create_arc(
            cx - track,
            cy - track,
            cx + track,
            cy + track,
            start=tk_start,
            extent=-extent,
            style="arc",
            outline=AMBER,
            width=self.RING,
        )
        # Liseré intérieur plus clair sur l'arc
        self.canvas.create_arc(
            cx - track,
            cy - track,
            cx + track,
            cy + track,
            start=tk_start,
            extent=-extent,
            style="arc",
            outline="#f5c078",
            width=max(3, self.RING // 5),
        )

        # Graduations 24 h
        for hour in range(24):
            angle = self._minutes_to_angle(hour * 60)
            major = hour % 3 == 0
            tick_len = 11 if major else 6
            outer = self._point(angle, r - self.RING / 2 - 1)
            inner_pt = self._point(angle, r - self.RING / 2 - 1 - tick_len)
            self.canvas.create_line(
                outer[0],
                outer[1],
                inner_pt[0],
                inner_pt[1],
                fill=self.TICK_MAJOR if major else self.TICK,
                width=2 if major else 1,
            )
            if major:
                label_pos = self._point(angle, r - self.RING / 2 - 26)
                text = "00" if hour == 0 else f"{hour:02d}"
                self.canvas.create_text(
                    label_pos[0],
                    label_pos[1],
                    text=text,
                    fill=MUTED if hour not in (0, 12) else TEXT,
                    font=(UI_FONT, 8, "bold" if hour in (0, 12) else "normal"),
                )

        # Durée au centre
        hours = schedule_duration_hours(
            _hhmm_from_minutes(start_m), _hhmm_from_minutes(end_m)
        )
        if abs(hours - round(hours)) < 0.01:
            duration_txt = f"{int(round(hours))} h"
        else:
            h = int(hours)
            m = int(round((hours - h) * 60))
            duration_txt = f"{h} h {m:02d}"
        self.canvas.create_text(
            cx, cy - 8, text=duration_txt, fill=TEXT, font=(UI_FONT, 22, "bold")
        )
        self.canvas.create_text(
            cx, cy + 14, text="durée", fill=MUTED, font=(UI_FONT, 9)
        )

        self._draw_handle(start_a, "start")
        self._draw_handle(end_a, "end")

        self.start_lbl.configure(text=_hhmm_from_minutes(start_m))
        self.end_lbl.configure(text=_hhmm_from_minutes(end_m))

    def _draw_handle(self, angle: float, which: str) -> None:
        x, y = self._point(angle)
        r = self.HANDLE
        # Ombre douce
        self.canvas.create_oval(
            x - r + 1,
            y - r + 2,
            x + r + 1,
            y + r + 2,
            fill="#0c0e12",
            outline="",
        )
        accent = AMBER if which == "start" else GREEN
        self.canvas.create_oval(
            x - r,
            y - r,
            x + r,
            y + r,
            fill="#1e222b",
            outline=accent,
            width=3,
        )
        self.canvas.create_oval(
            x - r + 4,
            y - r + 4,
            x + r - 4,
            y + r - 4,
            fill="#252a34",
            outline="",
        )
        glyph = "☾" if which == "start" else "☀"
        self.canvas.create_text(
            x, y, text=glyph, fill=accent, font=(UI_FONT, 13, "bold")
        )


class LuminositeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LuminoMint")
        self.resizable(False, False)
        self.configure(bg=BG)

        require_xrandr()
        self.output = detect_output()
        self._updating = False
        self._compact = False
        self._dragging = False
        self._drag_offset = (0, 0)
        self._icon_cache: dict[tuple[str, str, int], tk.PhotoImage] = {}
        self._schedule_job: str | None = None
        self._schedule_enabled = False

        self._build_ui()
        self._load_schedule_into_ui()
        self._load_current()
        self._enable_window_drag(self.full_frame)
        self._set_undecorated(True)
        self.enter_compact()
        self._tick_schedule()

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Up>", lambda _e: self.adjust(STEP))
        self.bind("<Down>", lambda _e: self.adjust(-STEP))
        self.bind("<Left>", lambda _e: self.adjust(-STEP))
        self.bind("<Right>", lambda _e: self.adjust(STEP))
        self.bind("<plus>", lambda _e: self.adjust(STEP))
        self.bind("<minus>", lambda _e: self.adjust(-STEP))
        self.bind("<KP_Add>", lambda _e: self.adjust(STEP))
        self.bind("<KP_Subtract>", lambda _e: self.adjust(-STEP))
        self.bind("<n>", lambda _e: self.toggle_night_shift())
        self.bind("<N>", lambda _e: self.toggle_night_shift())
        self.bind("<less>", lambda _e: self.adjust_night_shift(-NIGHT_SHIFT_STEP))
        self.bind("<greater>", lambda _e: self.adjust_night_shift(NIGHT_SHIFT_STEP))
        self.bind("<comma>", lambda _e: self.adjust_night_shift(-NIGHT_SHIFT_STEP))
        self.bind("<period>", lambda _e: self.adjust_night_shift(NIGHT_SHIFT_STEP))

    def _icon_button(
        self,
        parent: tk.Misc,
        name: str,
        color: str,
        command,
        size: int = 20,
        pad: int = 7,
        bg: str = BTN,
    ) -> tk.Button:
        icon = self._remix_icon(name, color, size)
        btn = tk.Button(
            parent,
            image=icon,
            command=command,
            bg=bg,
            activebackground=BTN_HOVER,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=pad,
            pady=pad,
            cursor="hand2",
        )
        btn.image = icon
        btn.bind("<Enter>", lambda _e, w=btn: w.configure(bg=BTN_HOVER))
        btn.bind("<Leave>", lambda _e, w=btn, rest=bg: w.configure(bg=rest))
        return btn

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        for name, accent in (("Bright", GREEN), ("Warm", AMBER)):
            style.configure(
                f"{name}.Horizontal.TScale",
                background=CARD,
                troughcolor="#2a2f38",
                bordercolor="#2a2f38",
                lightcolor=accent,
                darkcolor=accent,
                sliderthickness=18,
            )

        root = tk.Frame(self, bg=BG, padx=20, pady=18)
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_remove()
        self.full_frame = root
        root.columnconfigure(0, weight=1)

        header = tk.Frame(root, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        brand = self._remix_icon(ICON_SUN_FILL, GREEN, 26)
        brand_lbl = tk.Label(header, image=brand, bg=BG)
        brand_lbl.image = brand
        brand_lbl.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="n")

        tk.Label(
            header,
            text="LuminoMint",
            bg=BG,
            fg=TEXT,
            font=(UI_FONT, 16, "bold"),
        ).grid(row=0, column=1, sticky="w")

        screen = tk.Frame(header, bg=BG)
        screen.grid(row=1, column=1, sticky="w", pady=(2, 0))
        screen_icon = self._remix_icon(ICON_COMPUTER, MUTED, 14)
        screen_ic = tk.Label(screen, image=screen_icon, bg=BG)
        screen_ic.image = screen_icon
        screen_ic.pack(side="left")
        tk.Label(
            screen,
            text=self.output,
            bg=BG,
            fg=MUTED,
            font=(UI_FONT, 10),
        ).pack(side="left", padx=(6, 0))

        actions = tk.Frame(header, bg=BG)
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self._icon_button(
            actions, ICON_REFRESH, MUTED, self._load_current, size=18, pad=6
        ).pack(side="left", padx=(0, 6))
        self._icon_button(
            actions, ICON_COMPACT, TEXT, self.enter_compact, size=18, pad=6
        ).pack(side="left", padx=(0, 6))
        self._icon_button(
            actions, ICON_CLOSE, MUTED, self.destroy, size=18, pad=6
        ).pack(side="left")

        bright = tk.Frame(root, bg=CARD, padx=16, pady=14)
        bright.grid(row=1, column=0, sticky="ew", pady=(18, 10))
        bright.columnconfigure(1, weight=1)

        self.bright_card_icon = tk.Label(bright, bg=CARD)
        self.bright_card_icon.grid(row=0, column=0, padx=(0, 10), sticky="w")
        tk.Label(
            bright,
            text="Luminosité",
            bg=CARD,
            fg=TEXT,
            font=(UI_FONT, 11),
        ).grid(row=0, column=1, sticky="w")
        self.value_var = tk.StringVar(value="—")
        self.bright_value_lbl = tk.Label(
            bright,
            textvariable=self.value_var,
            bg=CARD,
            fg=GREEN,
            font=(UI_FONT, 20, "bold"),
        )
        self.bright_value_lbl.grid(row=0, column=2, sticky="e")

        slider_row = tk.Frame(bright, bg=CARD)
        slider_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        slider_row.columnconfigure(1, weight=1)

        self._icon_button(
            slider_row,
            ICON_SUBTRACT,
            MUTED,
            lambda: self.adjust(-STEP),
            size=18,
            pad=6,
            bg=BTN,
        ).grid(row=0, column=0, padx=(0, 10))

        self.brightness = tk.DoubleVar(value=1.0)
        self.scale = ttk.Scale(
            slider_row,
            from_=MIN_BRIGHTNESS,
            to=MAX_BRIGHTNESS,
            orient="horizontal",
            length=260,
            variable=self.brightness,
            command=self._on_scale,
            style="Bright.Horizontal.TScale",
        )
        self.scale.grid(row=0, column=1, sticky="ew")
        self._bind_scale_jump(self.scale)

        self._icon_button(
            slider_row,
            ICON_ADD,
            GREEN,
            lambda: self.adjust(STEP),
            size=18,
            pad=6,
            bg=BTN,
        ).grid(row=0, column=2, padx=(10, 0))

        night = tk.Frame(root, bg=CARD, padx=16, pady=14)
        night.grid(row=2, column=0, sticky="ew")
        night.columnconfigure(1, weight=1)

        self.night_card_icon = tk.Label(night, bg=CARD)
        self.night_card_icon.grid(row=0, column=0, padx=(0, 10), sticky="nw")
        titles = tk.Frame(night, bg=CARD)
        titles.grid(row=0, column=1, sticky="w")
        tk.Label(
            titles,
            text="Night Shift",
            bg=CARD,
            fg=TEXT,
            font=(UI_FONT, 11),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="Filtre lumière anti-bleu",
            bg=CARD,
            fg=MUTED,
            font=(UI_FONT, 9),
        ).pack(anchor="w")

        night_vals = tk.Frame(night, bg=CARD)
        night_vals.grid(row=0, column=2, sticky="e")
        self.night_value_var = tk.StringVar(value="—")
        self.night_value_lbl = tk.Label(
            night_vals,
            textvariable=self.night_value_var,
            bg=CARD,
            fg=AMBER,
            font=(UI_FONT, 20, "bold"),
        )
        self.night_value_lbl.pack(anchor="e")
        self.night_kelvin_var = tk.StringVar(value="")
        tk.Label(
            night_vals,
            textvariable=self.night_kelvin_var,
            bg=CARD,
            fg=MUTED,
            font=(UI_FONT, 9),
        ).pack(anchor="e")

        self.night_shift = tk.DoubleVar(value=0.0)
        self.night_scale = ttk.Scale(
            night,
            from_=MIN_NIGHT_SHIFT,
            to=MAX_NIGHT_SHIFT,
            orient="horizontal",
            length=260,
            variable=self.night_shift,
            command=self._on_night_scale,
            style="Warm.Horizontal.TScale",
        )
        self.night_scale.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(14, 12))
        self._bind_scale_jump(self.night_scale)

        toggle_icon = self._remix_icon(ICON_MOON_LINE, MUTED, 18)
        self.night_toggle = tk.Button(
            night,
            text="  Activer",
            image=toggle_icon,
            compound="left",
            command=self.toggle_night_shift,
            bg=BTN,
            fg=TEXT,
            activebackground=BTN_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=(UI_FONT, 10, "bold"),
        )
        self.night_toggle.image = toggle_icon
        self.night_toggle.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.night_toggle.bind("<Enter>", lambda _e: self.night_toggle.configure(bg=BTN_HOVER))
        self.night_toggle.bind("<Leave>", lambda _e: self.night_toggle.configure(bg=BTN))

        schedule = tk.Frame(night, bg=CARD)
        schedule.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(14, 0))

        self.schedule_start_var = tk.StringVar(value="22:00")
        self.schedule_end_var = tk.StringVar(value="07:00")

        self.schedule_btn = tk.Button(
            schedule,
            text="Programmer",
            command=self.toggle_schedule,
            bg=BTN,
            fg=TEXT,
            activebackground=BTN_HOVER,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=(UI_FONT, 10, "bold"),
        )
        self.schedule_btn.pack(fill="x")
        self.schedule_btn.bind("<Enter>", lambda _e: self.schedule_btn.configure(bg=BTN_HOVER))
        self.schedule_btn.bind(
            "<Leave>",
            lambda _e: self.schedule_btn.configure(
                bg=AMBER if self._schedule_enabled else BTN
            ),
        )

        self.schedule_status_var = tk.StringVar(value="")
        tk.Label(
            schedule,
            textvariable=self.schedule_status_var,
            bg=CARD,
            fg=MUTED,
            font=(UI_FONT, 9),
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.schedule_wheel = ScheduleWheel(
            schedule,
            self.schedule_start_var,
            self.schedule_end_var,
            on_change=self._on_schedule_wheel_change,
        )
        # Masquée tant que la programmation n'est pas activée
        self.schedule_wheel.pack_forget()

        tk.Label(
            root,
            text="↑ ↓   + −   N   < >     ·     icône fenêtre : mode réduit",
            bg=BG,
            fg="#5c6169",
            font=(UI_FONT, 8),
        ).grid(row=3, column=0, pady=(14, 0))

        compact = tk.Frame(self, bg=BG, padx=8, pady=8)
        compact.grid(row=0, column=0, sticky="nsew")
        self.compact_frame = compact
        compact.bind("<ButtonPress-1>", self._start_drag)
        compact.bind("<B1-Motion>", self._on_drag)
        compact.bind("<ButtonRelease-1>", self._stop_drag)

        self.compact_bright_btn = self._icon_button(
            compact, ICON_SUN_LINE, GREEN, self.cycle_compact_brightness, size=28, pad=10
        )
        self.compact_bright_btn.grid(row=0, column=0, padx=(0, 4))

        self.compact_night_btn = self._icon_button(
            compact, ICON_MOON_LINE, MUTED, self.toggle_compact_night, size=28, pad=10
        )
        self.compact_night_btn.grid(row=0, column=1, padx=4)

        self.compact_expand_btn = self._icon_button(
            compact, ICON_EXPAND, TEXT, self.exit_compact, size=28, pad=10
        )
        self.compact_expand_btn.grid(row=0, column=2, padx=4)

        self.compact_close_btn = self._icon_button(
            compact, ICON_CLOSE, MUTED, self.destroy, size=28, pad=10
        )
        self.compact_close_btn.grid(row=0, column=3, padx=(4, 0))

    def _format(self, value: float) -> str:
        return f"{int(round(value * 100))} %"

    def _format_night(self, intensity: float) -> str:
        if intensity <= 0.005:
            return "Off"
        return f"{int(round(intensity * 100))} %"

    def _sync_night_toggle(self, intensity: float) -> None:
        if intensity > 0.005:
            icon = self._remix_icon(ICON_MOON_FILL, AMBER, 18)
            self.night_toggle.configure(
                text="  Désactiver",
                image=icon,
                fg=AMBER,
                activeforeground=AMBER,
            )
        else:
            icon = self._remix_icon(ICON_MOON_LINE, MUTED, 18)
            self.night_toggle.configure(
                text="  Activer",
                image=icon,
                fg=TEXT,
                activeforeground=TEXT,
            )
        self.night_toggle.image = icon

    def _apply(self, brightness: float, night_shift: float | None = None) -> None:
        if night_shift is None:
            night_shift = float(self.night_shift.get())
        try:
            applied_b, applied_n = set_display(self.output, brightness, night_shift)
        except subprocess.CalledProcessError as exc:
            messagebox.showerror(
                "Erreur",
                f"Impossible d'appliquer les réglages.\n{exc.stderr or exc}",
            )
            return
        self._updating = True
        self.brightness.set(applied_b)
        self.value_var.set(self._format(applied_b))
        self.night_shift.set(applied_n)
        self.night_value_var.set(self._format_night(applied_n))
        self.night_kelvin_var.set(f"{night_shift_to_kelvin(applied_n)} K")
        self._sync_night_toggle(applied_n)
        self._sync_full_icons(applied_b, applied_n)
        self._sync_compact_buttons(applied_b, applied_n)
        self._updating = False

    def _bind_scale_jump(self, scale: ttk.Scale) -> None:
        """Clic / glisser : le curseur suit la position, pas les extrêmes ttk."""
        scale.bind("<Button-1>", self._on_scale_jump)
        scale.bind("<B1-Motion>", self._on_scale_jump)

    def _scale_value_at(self, scale: ttk.Scale, x: int) -> float:
        low = float(scale.cget("from"))
        high = float(scale.cget("to"))
        width = max(scale.winfo_width(), 1)
        # Marge = moitié du curseur, pour que le clic corresponde au centre
        pad = max(8, int(scale.winfo_height() * 0.45))
        usable = max(1, width - 2 * pad)
        fraction = _clamp((x - pad) / usable, 0.0, 1.0)
        return low + fraction * (high - low)

    def _on_scale_jump(self, event: tk.Event) -> str:
        event.widget.set(self._scale_value_at(event.widget, event.x))
        return "break"

    def _on_scale(self, _raw: str) -> None:
        if self._updating:
            return
        self._apply(float(self.brightness.get()))

    def _on_night_scale(self, _raw: str) -> None:
        if self._updating:
            return
        self._apply(float(self.brightness.get()), float(self.night_shift.get()))

    def adjust(self, delta: float) -> None:
        self._apply(float(self.brightness.get()) + delta)

    def adjust_night_shift(self, delta: float) -> None:
        self._apply(
            float(self.brightness.get()),
            float(self.night_shift.get()) + delta,
        )

    def toggle_night_shift(self) -> None:
        current = float(self.night_shift.get())
        target = 0.0 if current > 0.005 else 0.50
        self._apply(float(self.brightness.get()), target)

    def _load_current(self) -> None:
        try:
            current = get_brightness(self.output)
            night = gamma_to_night_shift(get_gamma(self.output))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Erreur", str(exc))
            return
        self._updating = True
        self.brightness.set(current)
        self.value_var.set(self._format(current))
        self.night_shift.set(night)
        self.night_value_var.set(self._format_night(night))
        self.night_kelvin_var.set(f"{night_shift_to_kelvin(night)} K")
        self._sync_night_toggle(night)
        self._sync_full_icons(current, night)
        self._sync_compact_buttons(current, night)
        self._updating = False

    def _fit_window(self) -> None:
        self.update_idletasks()
        self.geometry("")

    def _remix_icon(self, name: str, color: str, size: int = ICON_SIZE) -> tk.PhotoImage:
        key = (name, color, size)
        if key not in self._icon_cache:
            self._icon_cache[key] = load_remix_icon(name, color, size)
        return self._icon_cache[key]

    def _sync_full_icons(self, brightness: float, night_shift: float) -> None:
        if brightness < 0.375:
            sun = self._remix_icon(ICON_SUN_LINE, GREEN_DIM, 22)
            self.bright_value_lbl.configure(fg=GREEN_DIM)
        elif brightness < 0.75:
            sun = self._remix_icon(ICON_SUN_LINE, GREEN, 22)
            self.bright_value_lbl.configure(fg=GREEN)
        else:
            sun = self._remix_icon(ICON_SUN_FILL, GREEN_BRIGHT, 22)
            self.bright_value_lbl.configure(fg=GREEN_BRIGHT)
        self.bright_card_icon.configure(image=sun)
        self.bright_card_icon.image = sun

        if night_shift > 0.005:
            moon = self._remix_icon(ICON_MOON_FILL, AMBER, 22)
            self.night_value_lbl.configure(fg=AMBER)
        else:
            moon = self._remix_icon(ICON_MOON_LINE, MUTED, 22)
            self.night_value_lbl.configure(fg=MUTED)
        self.night_card_icon.configure(image=moon)
        self.night_card_icon.image = moon

    def _sync_compact_buttons(self, brightness: float, night_shift: float) -> None:
        if brightness < 0.375:
            sun = self._remix_icon(ICON_SUN_LINE, "#4e8f68")
        elif brightness < 0.75:
            sun = self._remix_icon(ICON_SUN_LINE, "#7dd3a0")
        else:
            sun = self._remix_icon(ICON_SUN_FILL, "#c8f5d8")
        self.compact_bright_btn.configure(image=sun)
        self.compact_bright_btn.image = sun

        if night_shift > 0.005:
            moon = self._remix_icon(ICON_MOON_FILL, "#f0b060")
        else:
            moon = self._remix_icon(ICON_MOON_LINE, "#9aa0a6")
        self.compact_night_btn.configure(image=moon)
        self.compact_night_btn.image = moon

    def _set_undecorated(self, enabled: bool) -> None:
        """Retire ou restaure la barre de titre du gestionnaire de fenêtres."""
        self.withdraw()
        self.overrideredirect(enabled)
        self.deiconify()

    def _is_interactive(self, widget: tk.Misc) -> bool:
        return isinstance(
            widget, (tk.Button, ttk.Scale, ttk.Button, tk.Entry, ttk.Entry, tk.Canvas)
        )

    def _enable_window_drag(self, widget: tk.Misc) -> None:
        if self._is_interactive(widget):
            return
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._on_drag)
        widget.bind("<ButtonRelease-1>", self._stop_drag)
        for child in widget.winfo_children():
            self._enable_window_drag(child)

    def _start_drag(self, event: tk.Event) -> None:
        if self._is_interactive(event.widget):
            return
        self._dragging = True
        self._drag_offset = (
            event.x_root - self.winfo_x(),
            event.y_root - self.winfo_y(),
        )

    def _on_drag(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _stop_drag(self, _event: tk.Event) -> None:
        self._dragging = False

    def enter_compact(self) -> None:
        self._compact = True
        self.full_frame.grid_remove()
        self.compact_frame.grid()
        self.attributes("-topmost", True)
        self._fit_window()

    def exit_compact(self) -> None:
        self._compact = False
        self.attributes("-topmost", False)
        self.compact_frame.grid_remove()
        self.full_frame.grid()
        self._fit_window()

    def cycle_compact_brightness(self) -> None:
        self._apply(next_compact_brightness(float(self.brightness.get())))

    def toggle_compact_night(self) -> None:
        current = float(self.night_shift.get())
        target = 0.0 if current > 0.005 else COMPACT_NIGHT_SHIFT
        self._apply(float(self.brightness.get()), target)

    def _set_schedule_wheel_visible(self, visible: bool) -> None:
        if visible:
            if not self.schedule_wheel.winfo_ismapped():
                self.schedule_wheel.pack(fill="x", pady=(12, 0))
                self.schedule_wheel.redraw()
        else:
            self.schedule_wheel.pack_forget()
        if not self._compact:
            self._fit_window()

    def _load_schedule_into_ui(self) -> None:
        schedule = load_schedule()
        self.schedule_wheel.set_times(str(schedule["start"]), str(schedule["end"]))
        self._schedule_enabled = bool(schedule["enabled"])
        self._set_schedule_wheel_visible(self._schedule_enabled)
        self._sync_schedule_ui(schedule)

    def _on_schedule_wheel_change(self) -> None:
        schedule = load_schedule()
        schedule["start"] = self.schedule_start_var.get()
        schedule["end"] = self.schedule_end_var.get()
        # Si déjà programmé, persiste la nouvelle plage tout de suite
        if self._schedule_enabled:
            schedule["enabled"] = True
            schedule = save_schedule(schedule)
        self._sync_schedule_ui(schedule)

    def _sync_schedule_ui(self, schedule: dict[str, object] | None = None) -> None:
        schedule = schedule or load_schedule()
        enabled = bool(schedule.get("enabled", False))
        self._schedule_enabled = enabled
        start = str(schedule.get("start", "22:00"))
        end = str(schedule.get("end", "07:00"))
        self._set_schedule_wheel_visible(enabled)
        if enabled:
            self.schedule_btn.configure(
                text="Déprogrammer",
                bg=AMBER,
                fg="#1a1208",
                activebackground="#f5c078",
                activeforeground="#1a1208",
            )
            desired = desired_night_from_schedule(schedule)
            state = "actif" if desired and desired > 0.005 else "hors plage"
            hours = schedule_duration_hours(start, end)
            self.schedule_status_var.set(
                f"{start} → {end} · {hours:g} h · {state}"
            )
        else:
            self.schedule_btn.configure(
                text="Programmer",
                bg=BTN,
                fg=TEXT,
                activebackground=BTN_HOVER,
                activeforeground=TEXT,
            )
            self.schedule_status_var.set("")

    def toggle_schedule(self) -> None:
        try:
            start = format_hhmm(self.schedule_start_var.get())
            end = format_hhmm(self.schedule_end_var.get())
        except ValueError as exc:
            messagebox.showerror("Programmation", str(exc))
            return

        if self._schedule_enabled:
            schedule = save_schedule(
                {
                    "enabled": False,
                    "start": start,
                    "end": end,
                    "intensity": load_schedule()["intensity"],
                }
            )
            self._sync_schedule_ui(schedule)
            return

        intensity = float(self.night_shift.get())
        if intensity <= 0.005:
            intensity = COMPACT_NIGHT_SHIFT
        schedule = save_schedule(
            {
                "enabled": True,
                "start": start,
                "end": end,
                "intensity": intensity,
            }
        )
        self.schedule_wheel.set_times(str(schedule["start"]), str(schedule["end"]))
        self._sync_schedule_ui(schedule)
        self._tick_schedule(force=True)

    def _tick_schedule(self, force: bool = False) -> None:
        if self._schedule_job is not None:
            try:
                self.after_cancel(self._schedule_job)
            except tk.TclError:
                pass
            self._schedule_job = None

        schedule = load_schedule()
        self._sync_schedule_ui(schedule)
        if schedule.get("enabled") or force:
            desired = desired_night_from_schedule(schedule)
            if desired is not None:
                current = float(self.night_shift.get())
                if abs(current - desired) >= 0.02:
                    self._apply(float(self.brightness.get()), desired)

        self._schedule_job = self.after(30_000, self._tick_schedule)


def main() -> None:
    if run_cli():
        return
    ensure_panel_applet()
    reload_applet()
    try:
        app = LuminositeApp()
    except Exception as exc:  # noqa: BLE001
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("LuminoMint", str(exc))
        root.destroy()
        raise SystemExit(1) from exc
    app.mainloop()


if __name__ == "__main__":
    main()
