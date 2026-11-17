# Configuration reference

Swipey Photos keeps its session settings in one small JSON file. There is no hidden
database and no `QSettings` blob — you can read, diff, edit and back up the file
by hand.

> This document describes the schema implemented in
> [`src/swipey_photos/utils/config.py`](../src/swipey_photos/utils/config.py).
> Read/write support landed with the core layer (M1); the UI writes the file when
> the window closes (M2).

## Location

| Purpose | Path |
| --- | --- |
| Configuration | `${XDG_CONFIG_HOME:-~/.config}/swipey-photos/config.json` |
| Log file | `${XDG_DATA_HOME:-~/.local/share}/swipey-photos/logs/swipey-photos.log` |
| Log rotations | same directory, `swipey-photos.log.1` … `.3` |

The file is created on the first save, with mode `0600`; its parent directory is
created with `0700`. Until then Swipey Photos runs on the built-in defaults and
never creates an empty file. Writes are atomic — a temporary file in the same
directory is `fsync`ed and then `os.replace`d — so a crash cannot leave a
half-written configuration behind.

## Precedence

Highest wins:

1. Command-line flags (`--config`, `--log-level`, …) — planned for M2
2. Environment variables — planned for M2
3. The config file
4. Built-in defaults

Today the loader reads only the file (plus `XDG_CONFIG_HOME`/
`XDG_DATA_HOME`); the upper layers arrive with the CLI.

## Complete example

```json
{
  "last_folder": "/home/you/Pictures/2024-06-trip",
  "recent_folders": [
    "/home/you/Pictures/2024-06-trip",
    "/home/you/Pictures/to-sort",
    "/home/you/Downloads/photos"
  ],
  "theme": "system",
  "version": 1,
  "window": {
    "height": 800,
    "width": 1200
  }
}
```

Keys are written in alphabetical order (`sort_keys=True`) and indented by two
spaces, so diffs stay small. Order is irrelevant when reading.

## Key reference

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `version` | integer | `1` | schema version. A value newer than the app supports falls back to defaults with a warning |
| `last_folder` | string or `null` | `null` | absolute path reopened at start-up; `null` or a blank string means "no folder yet" |
| `recent_folders` | array of strings | `[]` | up to five newest-first folders offered on the welcome page; blank and duplicate entries are dropped, extra entries are trimmed with a warning |
| `window.width` | integer | `1200` | remembered window width in logical pixels (200–20000) |
| `window.height` | integer | `800` | remembered window height in logical pixels (200–20000) |
| `theme` | string | `"system"` | `system`, `light` or `dark`; also switched from *View → Dark Mode*, which writes this key |

Unknown keys (top level or inside `window`) are logged at WARNING and ignored, so
a file written by a newer build still loads in an older one.

## Failure handling

| Situation | Behaviour |
| --- | --- |
| File missing | `default_config()` returned; nothing is written |
| Unreadable file (permissions, I/O) | `ConfigError` naming the path; the caller may continue with defaults |
| Malformed JSON | `ConfigError` with the parser message; the file is left untouched |
| JSON that is not an object | `ConfigError` ("config must be a JSON object") |
| Wrong value type | `ConfigValidationError` naming the key, e.g. `window.width must be an integer` |
| Out-of-range value | `ConfigValidationError` listing **every** problem in one message |
| Unknown key | WARNING, key ignored |
| Newer `version` | WARNING, defaults returned, file not rewritten |
| Directory not writable | `ConfigError` with the OS reason; no partial file remains |

The UI decides what to show; the loader never silently discards user settings.

## Environment variables

| Variable | Effect |
| --- | --- |
| `XDG_CONFIG_HOME` | base directory for the config file (default `~/.config`) |
| `XDG_DATA_HOME` | base directory for the log file (default `~/.local/share`) |
| `HOME` | fallback for both defaults |

Environment variables are read at call time, which is what lets the test suite
redirect everything with `monkeypatch.setenv`.

## Command-line flags

```text
swipey-photos [FOLDER] [options]

  FOLDER                  start with this folder (skips the welcome page)
  --version               print version and exit
  --config PATH           use an alternative config file
  --log-level LEVEL       DEBUG | INFO | WARNING | ERROR | CRITICAL
  -v, --verbose           log at DEBUG level and echo the log to stderr
```

`--no-config` and `--log-file` are not implemented yet. A broken config file is
not fatal: the app starts on defaults and shows a warning in the status bar.

## Recipes

**Reopen the last folder on start-up** — the app writes this for you, but you can
set it by hand:

```json
{ "last_folder": "/home/you/Pictures/to-sort" }
```

**Force the dark theme** — or just tick *View → Dark Mode*, which writes this key
for you:

```json
{ "theme": "dark" }
```

**Small laptop screen:**

```json
{ "window": { "width": 900, "height": 600 } }
```

**Start from scratch** — delete the file; defaults are back:

```bash
rm ~/.config/swipey-photos/config.json
```

## Reset and migration

```bash
# Back up, then reset
cp ~/.config/swipey-photos/config.json ~/.config/swipey-photos/config.json.bak
rm ~/.config/swipey-photos/config.json
```

The app writes a fresh file with defaults the next time it saves.

The top-level `version` key is the migration hook. When the schema changes, a
future loader can upgrade older files in memory and write the new schema on the
next save. Downgrades are not supported: a newer `version` yields defaults plus a
warning instead of guessing at unknown keys.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Settings do not stick | config directory not writable; check `ls -ld ~/.config/swipey-photos` and the log |
| App ignores my edits | invalid JSON earlier in the file — validate with `python -m json.tool ~/.config/swipey-photos/config.json` |
| "window.width must be an integer" | JSON has a string where a number belongs (`"width": "800"`) |
| Window opens at the default size | `window.width`/`height` outside 200–20000, or the file failed to parse (see the log) |
| Theme keeps reverting to system | `theme` is not one of `system`, `light`, `dark` |
| Config path confusion | run with `--log-level DEBUG` (M2) and look for the `loaded config from …` line |
