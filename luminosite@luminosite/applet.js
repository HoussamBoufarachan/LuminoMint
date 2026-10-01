const Applet = imports.ui.applet;
const AppletManager = imports.ui.appletManager;
const Clutter = imports.gi.Clutter;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Mainloop = imports.mainloop;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Tooltips = imports.ui.tooltips;
const Util = imports.misc.util;

const MIN_BRIGHTNESS = 0.05;
const MAX_BRIGHTNESS = 1.05;
const BRIGHTNESS_SPAN = MAX_BRIGHTNESS - MIN_BRIGHTNESS;

class GaugeSlider extends PopupMenu.PopupSliderMenuItem {
    constructor(applet, iconName, label, kind) {
        super(0);
        this._applet = applet;
        this._kind = kind;
        this._seeking = false;
        this._label = label;
        this._applyId = 0;

        this.icon = new St.Icon({
            icon_name: iconName,
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 16,
        });
        this.removeActor(this._slider);
        this.addActor(this.icon, { span: 0 });
        this.addActor(this._slider, { span: -1, expand: true });

        this.tooltip = new Tooltips.Tooltip(this.actor, label);
        this.connect("drag-begin", () => { this._seeking = true; });
        this.connect("drag-end", () => {
            this._seeking = false;
            this._flushNow();
        });
        this.connect("value-changed", (_slider, value) => this._onValueChanged(value));
    }

    _onValueChanged(value) {
        this._updateTooltip(value);
        if (this._applyId) {
            Mainloop.source_remove(this._applyId);
            this._applyId = 0;
        }
        this._applyId = Mainloop.timeout_add(60, () => {
            this._applyId = 0;
            this._applet._setFromSlider(this._kind, value);
            return false;
        });
    }

    _flushNow() {
        if (this._applyId) {
            Mainloop.source_remove(this._applyId);
            this._applyId = 0;
        }
        this._applet._setFromSlider(this._kind, this._value);
    }

    setFromStatus(rawValue) {
        if (this._seeking)
            return;
        let sliderValue = this._kind === "brightness"
            ? this._applet._brightnessToSlider(rawValue)
            : Math.max(0, Math.min(1, Number(rawValue) || 0));
        this.setValue(sliderValue);
        this._updateTooltip(sliderValue);
    }

    _updateTooltip(sliderValue) {
        let label;
        if (this._kind === "brightness") {
            let brightness = this._applet._sliderToBrightness(sliderValue);
            label = `${this._label}: ${Math.round(brightness * 100)} %`;
        } else {
            let night = Math.max(0, Math.min(1, sliderValue));
            label = night <= 0.005
                ? `${this._label}: Off`
                : `${this._label}: ${Math.round(night * 100)} %`;
        }
        this.tooltip.set_text(label);
    }
}

class LuminositeApplet extends Applet.Applet {
    constructor(metadata, orientation, panel_height, instance_id) {
        super(orientation, panel_height, instance_id);
        this.metadata = metadata;
        this.setAllowedLayout(Applet.AllowedLayout.BOTH);

        this._script = this._findScript();
        this._busy = false;
        this._refreshId = 0;
        this._queued = { brightness: 0, night: 0 };
        this._hoverKind = "brightness";
        this._pendingSet = { brightness: null, night: null };
        this._status = {
            brightness: 1,
            night_shift: 0,
            brightness_label: "—",
            night_label: "Off",
            kelvin: 6500,
            output: "",
        };

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);
        this.menu.connect("open-state-changed", (_menu, open) => {
            if (open)
                this._run(["--apply-schedule"]);
        });

        this.brightnessSlider = new GaugeSlider(
            this,
            "display-brightness-symbolic",
            _("Luminosité"),
            "brightness"
        );
        this.nightSlider = new GaugeSlider(
            this,
            "weather-clear-night-symbolic",
            _("Night Shift"),
            "night"
        );
        this.menu.addMenuItem(this.brightnessSlider);
        this.menu.addMenuItem(this.nightSlider);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let openUiItem = new PopupMenu.PopupIconMenuItem(
            _("Ouvrir l'interface complète"),
            "display-brightness-symbolic",
            St.IconType.SYMBOLIC
        );
        openUiItem.connect("activate", () => this._openFullUi());
        this.menu.addMenuItem(openUiItem);

        this.box = new St.BoxLayout({
            style_class: "luminosite-box",
            reactive: true,
            track_hover: false,
        });
        this.actor.add(this.box);

        this.brightIcon = new St.Icon({
            icon_name: "display-brightness-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            style_class: "applet-icon",
        });
        this.brightButton = new St.Button({
            child: this.brightIcon,
            style_class: "applet-box luminosite-button luminosite-sun",
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this.brightButton.connect("clicked", () => this._openMenu());
        this.brightButton.connect("enter-event", () => { this._hoverKind = "brightness"; });
        this.brightButton.connect("scroll-event", (_actor, event) => this._onScroll(event, "brightness"));
        this.box.add_actor(this.brightButton);

        this.nightIcon = new St.Icon({
            icon_name: "weather-clear-night-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            style_class: "applet-icon",
        });
        this.nightButton = new St.Button({
            child: this.nightIcon,
            style_class: "applet-box luminosite-button luminosite-moon-off",
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        this.nightButton.connect("clicked", () => this._openMenu());
        this.nightButton.connect("enter-event", () => { this._hoverKind = "night"; });
        this.nightButton.connect("scroll-event", (_actor, event) => this._onScroll(event, "night"));
        this.box.add_actor(this.nightButton);
        this.actor.connect("scroll-event", (_actor, event) => this._onScroll(event, this._hoverKind));

        this.brightTip = new Tooltips.Tooltip(this.brightButton, _("Luminosité"));
        this.nightTip = new Tooltips.Tooltip(this.nightButton, _("Night Shift"));

        let openItem = new PopupMenu.PopupIconMenuItem(
            _("Ouvrir l'interface complète"),
            "display-brightness-symbolic",
            St.IconType.SYMBOLIC
        );
        openItem.connect("activate", () => this._openFullUi());
        this._applet_context_menu.addMenuItem(openItem);

        let refreshItem = new PopupMenu.PopupIconMenuItem(
            _("Actualiser"),
            "view-refresh-symbolic",
            St.IconType.SYMBOLIC
        );
        refreshItem.connect("activate", () => this._run(["--apply-schedule"]));
        this._applet_context_menu.addMenuItem(refreshItem);

        this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let closeItem = new PopupMenu.PopupIconMenuItem(
            _("Fermer l'app"),
            "window-close-symbolic",
            St.IconType.SYMBOLIC
        );
        closeItem.connect("activate", () => this._closeApp());
        this._applet_context_menu.addMenuItem(closeItem);

        this.on_orientation_changed(orientation);
        this._updateIconSize();
        this._run(["--apply-schedule"]);
        this._refreshId = Mainloop.timeout_add_seconds(30, () => {
            this._run(["--apply-schedule"]);
            return true;
        });
    }

    _brightnessToSlider(brightness) {
        return Math.max(0, Math.min(1, (Number(brightness) - MIN_BRIGHTNESS) / BRIGHTNESS_SPAN));
    }

    _sliderToBrightness(sliderValue) {
        return MIN_BRIGHTNESS + Math.max(0, Math.min(1, sliderValue)) * BRIGHTNESS_SPAN;
    }

    _openMenu() {
        this.menu.toggle();
    }

    on_applet_clicked(_event) {
        this._openMenu();
    }

    _findScript() {
        let candidates = [];
        try {
            let dir = Gio.File.new_for_path(this.metadata.path);
            let info = dir.query_info(
                "standard::is-symlink,standard::symlink-target",
                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                null
            );
            let appletDir = this.metadata.path;
            if (info.get_is_symlink()) {
                let target = info.get_symlink_target();
                if (target) {
                    appletDir = target.indexOf("/") === 0
                        ? target
                        : GLib.build_filenamev([GLib.path_get_dirname(this.metadata.path), target]);
                }
            }
            candidates.push(GLib.build_filenamev([appletDir, "..", "luminosite.py"]));
        } catch (e) {
            candidates.push(GLib.build_filenamev([this.metadata.path, "..", "luminosite.py"]));
        }
        candidates.push("/media/houss/disk_D17/prv/luminosite/luminosite.py");

        for (let path of candidates) {
            if (GLib.file_test(path, GLib.FileTest.IS_REGULAR))
                return path;
        }
        return candidates[candidates.length - 1];
    }

    _updateIconSize() {
        let size = this.getPanelIconSize(St.IconType.SYMBOLIC);
        if (!size)
            return;
        this.brightIcon.set_icon_size(size);
        this.nightIcon.set_icon_size(size);
    }

    on_orientation_changed(orientation) {
        this.orientation = orientation;
        let vertical = orientation === St.Side.LEFT || orientation === St.Side.RIGHT;
        this.box.set_vertical(vertical);
        if (this.menu)
            this.menu.setArrowSide(orientation);
    }

    on_panel_icon_size_changed() {
        this._updateIconSize();
    }

    on_panel_height_changed() {
        this._updateIconSize();
    }

    on_applet_removed_from_panel() {
        if (this._refreshId) {
            Mainloop.source_remove(this._refreshId);
            this._refreshId = 0;
        }
    }

    _onScroll(event, kind) {
        let dir = event.get_scroll_direction();
        let delta = 0;

        if (dir === Clutter.ScrollDirection.SMOOTH) {
            let [, dy] = event.get_scroll_delta();
            if (!dy)
                return Clutter.EVENT_PROPAGATE;
            delta = dy < 0 ? 0.05 : -0.05;
        } else if (dir === Clutter.ScrollDirection.UP) {
            delta = 0.05;
        } else if (dir === Clutter.ScrollDirection.DOWN) {
            delta = -0.05;
        } else {
            return Clutter.EVENT_PROPAGATE;
        }

        this._queueAdjust(kind, delta);
        return Clutter.EVENT_STOP;
    }

    _queueAdjust(kind, delta) {
        if (kind === "night")
            this._queued.night += delta;
        else
            this._queued.brightness += delta;
        this._flushQueue();
    }

    _flushQueue() {
        if (this._busy)
            return;
        if (this._pendingSet.brightness !== null) {
            let value = this._pendingSet.brightness;
            this._pendingSet.brightness = null;
            this._run([`--set-brightness=${value}`]);
            return;
        }
        if (this._pendingSet.night !== null) {
            let value = this._pendingSet.night;
            this._pendingSet.night = null;
            this._run([`--set-night=${value}`]);
            return;
        }
        if (this._queued.brightness) {
            let delta = this._queued.brightness;
            this._queued.brightness = 0;
            this._run([`--adjust-brightness=${delta}`]);
            return;
        }
        if (this._queued.night) {
            let delta = this._queued.night;
            this._queued.night = 0;
            this._run([`--adjust-night=${delta}`]);
        }
    }

    _setFromSlider(kind, sliderValue) {
        if (kind === "brightness") {
            this._pendingSet.brightness = Number(this._sliderToBrightness(sliderValue).toFixed(2));
        } else {
            this._pendingSet.night = Number(Math.max(0, Math.min(1, sliderValue)).toFixed(2));
        }
        this._flushQueue();
    }

    _openFullUi() {
        Util.spawnCommandLine(`python3 '${this._script.replace(/'/g, "'\\''")}'`);
    }

    _closeApp() {
        if (this._script)
            Util.spawnCommandLine(`pkill -f '${this._script.replace(/'/g, "'\\''")}'`);
        AppletManager._removeAppletFromPanel(this._uuid, this.instance_id);
    }

    _run(extraArgs) {
        if (!this._script)
            return;
        let isStatus = extraArgs.length === 1 && (
            extraArgs[0] === "--status" || extraArgs[0] === "--apply-schedule"
        );
        if (this._busy)
            return;
        if (!GLib.file_test(this._script, GLib.FileTest.IS_REGULAR)) {
            this.set_applet_tooltip(_("Script luminosite.py introuvable"));
            return;
        }
        this._busy = !isStatus;
        let argv = ["python3", this._script].concat(extraArgs);
        Util.spawnCommandLineAsyncIO("", (stdout, stderr, exitCode) => {
            this._busy = false;
            if (exitCode !== 0) {
                let message = (stderr || _("Impossible d'appliquer le réglage")).trim();
                this.set_applet_tooltip(message);
                global.logError(`LuminoMint: ${message}`);
                this._flushQueue();
                return;
            }
            try {
                this._applyStatus(JSON.parse(stdout));
            } catch (e) {
                global.logError(e);
            }
            this._flushQueue();
        }, { argv });
    }

    _applyStatus(data) {
        this._status = data;
        let nightOn = Number(data.night_shift) > 0.005;
        this.nightButton.style_class = nightOn
            ? "applet-box luminosite-button luminosite-moon-on"
            : "applet-box luminosite-button luminosite-moon-off";

        this.brightnessSlider.setFromStatus(data.brightness);
        this.nightSlider.setFromStatus(data.night_shift);

        let bright = `${data.brightness_label}`;
        let night = nightOn ? `${data.night_label} · ${data.kelvin} K` : "Off";
        let schedule = data.schedule || {};
        let scheduleTip = "";
        if (schedule.enabled) {
            scheduleTip = `\n${_("Programmé")} ${schedule.start} → ${schedule.end}`;
        }
        this.brightTip.set_text(`${_("Luminosité")} : ${bright}\n${_("Clic")} : jauge`);
        this.nightTip.set_text(`${_("Night Shift")} : ${night}${scheduleTip}\n${_("Clic")} : jauge`);
        this.set_applet_tooltip(`${data.output} · ${bright} · Night Shift ${night}${scheduleTip}`);
    }
}

function main(metadata, orientation, panel_height, instance_id) {
    return new LuminositeApplet(metadata, orientation, panel_height, instance_id);
}
