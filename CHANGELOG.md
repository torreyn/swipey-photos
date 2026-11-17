# Changelog

All notable changes to Swipey Photos are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `0.x` series was the internal development track (milestones `M0`–`M4` in the
README roadmap). It was never tagged or published, so the first entry below is
the first public release; `0.1.0` therefore never existed as a downloadable
artefact. New entries go under `[Unreleased]` and move down when a tag is cut —
`tests/test_packaging.py` fails if the shipped version has no section here.

## [Unreleased]

### Added

- The About box has a **Buy me a coffee** button that opens
  <https://buymeacoffee.com/2re.me> in the default browser
  (`ui.branding.SUPPORT_URL`); *Close* stays the default action.

### Changed

- The app is now **Swipey Photos**. The rename covers the import package
  (`swipey_photos`), the command (`swipey-photos`), the desktop entry and icon
  stem (`swipey-photos`), the logger namespace, and the state directories
  (`~/.config/swipey-photos/`, `~/.local/share/swipey-photos/logs/`). Because
  `1.0.0` was never tagged, there is nothing to migrate: reinstall (the old
  `image-swiper` command and config directory can be deleted).
- The four footer buttons now spell out the gesture they trigger — `← Bad`,
  `↓ OK`, `↑ Great`, `Good →` — so the swipe map is legible without hovering a
  tooltip. The labels live in `ui.main_window.CATEGORY_BUTTON_LABELS`.
- Removed the gesture legend that repeated those labels under the card. The
  stage is now exactly the card plus its caption, which returns the vertical
  space to the image.
- CI reports coverage (`pytest-cov`) and runs the GUI suite a second time on a
  virtual X server, so the `xcb` platform plugin is exercised too.
- Added a PyInstaller recipe (`swipey-photos.spec`), `scripts/build.sh` and a
  tag-triggered release workflow; `pip install ".[binary]"` is the only extra
  requirement for building a standalone executable.

### Fixed

- The About box's *Buy me a coffee* button now opens the browser for real. It
  went through `QDesktopServices.openUrl()`, which on Wayland desktops that
  route through `xdg-desktop-portal` returns `True` and opens nothing — the
  click looked like a no-op. The new `utils/browser.py` drives `xdg-open`, then
  `gio open`, then `webbrowser`, checks the exit status of each, and the window
  names the URL in the status bar when no launcher accepts it. The About text
  shows the URL as selectable text as well, so it can always be copied.

## [1.0.0] - 2026-11-17

First packaged release. The sorting loop, the comfort pass and the desktop
integration ship together; everything listed below is in the release artefact.

### Added

- **Four-way swipe sorting** — left → `Bad/`, right → `Good/`, up → `Great/`,
  down → `OK/`, with a drag threshold of about a third of the window width and a
  spring-back below it.
- **Keyboard parity** — arrows and WASD mirror every swipe, plus
  <kbd>Ctrl</kbd>+<kbd>Z</kbd> (undo), <kbd>Space</kbd> (skip),
  <kbd>Ctrl</kbd>+<kbd>O</kbd> (open folder), <kbd>F5</kbd> (rescan),
  <kbd>F11</kbd> (fullscreen), <kbd>F1</kbd> (shortcut overlay).
- **Non-destructive file moves** — collision-safe (`_1`, `_2`, … suffixes, never
  an overwrite), cross-device fallback, and an undo stack with a configurable
  depth. Nothing is ever deleted.
- **Image pipeline** — folder scan with validation, EXIF orientation, display-only
  downscaling of huge images, animated GIF first frames, and background prefetch
  of the next images so navigation stays responsive.
- **Swipe card** — rounded card with drop shadow, 150 ms entrance animation,
  rotation and directional colour feedback while dragging, badge on release and
  a fly-out before the next image appears.
- **Welcome and summary pages** — recent-folder shortcuts and a per-category
  tally with restart/pick/quit actions at the end of a folder.
- **Configuration and logs** — human-editable JSON at
  `${XDG_CONFIG_HOME}/swipey-photos/config.json` (window size, theme, last and
  recent folders), written atomically with mode `0600`; rotating logs with three
  backups under `${XDG_DATA_HOME}/swipey-photos/logs/`.
- **`--dry-run`** — logs every decision and touches no file, for rehearsing a
  sort; `--config` and `-v` for alternate settings and console logging.
- **Dark mode** — live palette switch from *View → Dark Mode*, or `"theme"` in
  the config file.
- **Desktop integration** — `.desktop` entry, generated `hicolor` icon tree
  (`packaging/icons/`), `packaging/install-desktop.sh` for user- or
  system-wide installs, and an AppImage build script that bundles CPython and
  PyQt6.

### Documentation

- `README.md` — installation, usage walkthrough, shortcut table, configuration,
  FAQ.
- `docs/ARCHITECTURE.md` — layer contracts, threading model, naming.
- `docs/CONFIGURATION.md` — key-by-key config reference.
- `docs/DEVELOPMENT.md` — test inventory and contribution workflow.
- `docs/PACKAGING.md` — desktop entry, AppImage, Flatpak status, release
  checklist.

### Known limitations

- Linux is the only supported target; the code stays toolkit-portable, but no
  Windows or macOS artefact is built.
- Flatpak is deferred — the runtime does not carry PyQt6 (see
  [`docs/PACKAGING.md` §5](docs/PACKAGING.md#5-flatpak)).
- Two-finger touchpad "flick" gestures depend on the compositor; the keyboard
  bindings are the reliable fallback.
- There is no PyPI release; install from a wheel, from a checkout, with
  `pipx install git+…`, or use the standalone binary.

[Unreleased]: https://github.com/torreyn/swipey-photos/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/torreyn/swipey-photos/releases/tag/v1.0.0
