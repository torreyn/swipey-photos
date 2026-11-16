# Documentation assets

Screenshots and mock-ups referenced from the README and docs.

## Current files

| File | Status | Used by |
| --- | --- | --- |
| `screenshot-main.svg` | placeholder mock-up (hand-drawn SVG) | `README.md` → Screenshots |

## Adding real screenshots (M2)

Planned names, so links in the docs stay stable:

| File | Content |
| --- | --- |
| `screenshot-main.png` | idle window with a photo card, 1440×900 |
| `screenshot-drag.gif` | a drag with the GOOD/BAD overlay becoming visible |
| `screenshot-summary.png` | completion screen with per-destination counts |
| `screenshot-shortcuts.png` | the F1 shortcut overlay |

Guidelines:

- Capture on a **clean session** with a neutral wallpaper; 1440×900 or
  1920×1080, PNG for stills, GIF/WebM for motion (keep GIFs under 5 MB).
- Use **generated or public-domain photos** — never personal pictures with
  faces, addresses or GPS coordinates.
- Strip metadata before committing: `exiftool -all= docs/assets/*.png`.
- Optimise: `oxipng -o4 --strip all docs/assets/*.png`.
- Update the image reference in `README.md` when `screenshot-main.png` lands,
  and delete this note when all four exist.

Commands that work on most desktops:

```bash
# KDE Plasma
spectacle -b -n -o docs/assets/screenshot-main.png

# GNOME
gnome-screenshot -f docs/assets/screenshot-main.png

# Any X11/Wayland session
flameshot gui
```
