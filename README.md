# LuminoMint

Contrôle de la luminosité d’écran et filtre Night Shift sous Linux, via `xrandr`.

- Interface graphique Tkinter (modes compact / étendu)
- Applet Cinnamon pour le panneau
- CLI pour scripts et bindings clavier
- Programmation horaire du Night Shift

## Prérequis

- Linux avec X11 et `xrandr` (`x11-xserver-utils`)
- Python 3.10+
- Pillow (icônes teintées)
- Cinnamon (optionnel, pour l’applet)

## Installation

```bash
# Cloner / se placer dans le dépôt
cd luminosite

# Environnement virtuel recommandé
python3 -m venv .venv
source .venv/bin/activate

# Dépendances runtime + outils de test
pip install -e ".[dev]"
```

Lancer l’interface :

```bash
python3 luminosite.py
# ou, après install editable :
luminomint
```

Installer / recharger l’applet Cinnamon (lien symbolique + panneau) :

```bash
python3 luminosite.py   # assure le symlink et recharge l’applet
# ou manuellement :
./reload-applet.sh
```

Fichier `.desktop` : adaptez la ligne `Exec=` à votre chemin d’installation, ou utilisez :

```bash
Exec=python3 /chemin/vers/luminosite/luminosite.py
```

## CLI

```bash
python3 luminosite.py --status
python3 luminosite.py --set-brightness 0.75
python3 luminosite.py --set-night 0.60
python3 luminosite.py --cycle-brightness
python3 luminosite.py --toggle-night
python3 luminosite.py --adjust-brightness 0.05
python3 luminosite.py --adjust-night -0.05
python3 luminosite.py --apply-schedule
```

La programmation Night Shift est stockée dans `~/.config/luminosite/schedule.json`.

## Tests

```bash
pip install -e ".[dev]"
pytest
# avec couverture :
pytest --cov=luminosite --cov-report=term-missing
```

Les tests unitaires couvrent la logique pure (couleur, gamma, horaires, clamp) sans dépendre d’un écran réel.

## Structure

```
luminosite.py              # Application + CLI LuminoMint
luminosite@luminosite/     # Applet Cinnamon
icons/                     # Remix Icon (PNG/SVG)
reload-applet.sh           # Recharge l’applet via D-Bus
tests/                     # Tests pytest
pyproject.toml             # Métadonnées, deps, config pytest
```

## Licence

MIT — voir [LICENSE](LICENSE).

Icônes : [Remix Icon](https://remixicon.com).
