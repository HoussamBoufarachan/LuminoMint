#!/usr/bin/env bash
set -euo pipefail

UUID="luminosite@luminosite"

dbus-send --session --type=method_call \
    --dest=org.Cinnamon \
    /org/Cinnamon \
    org.Cinnamon.ReloadXlet \
    "string:${UUID}" \
    string:APPLET

echo "Applet ${UUID} rechargée."
