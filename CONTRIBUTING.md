# Contributing to ImageSwiper

Thanks for considering a contribution! ImageSwiper is a small, focused Linux
desktop app, and every bug report, UX observation or patch helps.

By participating you agree to follow the
[Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Be kind, assume good intent, and critique code — not people.

---

## Ways to contribute

| Type | Where to start |
| --- | --- |
| 🐞 Bug report | Open an issue using the *Bug report* template; include distro, desktop session (X11/Wayland), Python and Qt versions, and the tail of the log file |
| 💡 Feature idea | Open an issue first so we can agree on scope before code is written |
| 🧑‍💻 Code | Pick an issue labelled `good first issue` or `help wanted` and comment that you are taking it |
| 🎨 Design / UX | Screenshots or mock-ups in an issue are very welcome; the swipe thresholds and animation timings need taste |
| 🌍 Translations | Not wired up yet (planned after 1.0); open an issue if you want to help |
| 📝 Docs | Typos, clearer instructions and distro-specific notes are always appreciated |

---

## Development setup

```bash
git clone https://github.com/torreyn/image-swiper.git
cd image-swiper

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Qt still needs a few system libraries; the apt/dnf/pacman commands are in
[README → Installation](README.md#1-system-packages-qt-runtime--python-tooling).

Verify the setup:

```bash
python -c "import image_swiper; print(image_swiper.__version__)"
pytest -q
```

---

## Layer boundaries (please respect these)

```text
app.py  →  ui/  →  core/  →  utils/
```

- **`ui/`** is the only layer allowed to import `PyQt6` (plus `app.py`).
- **`core/`** must stay toolkit-agnostic: pure Python and Pillow. It is unit
  tested without creating a `QApplication`.
- **`utils/`** knows nothing about images, Qt or the sorting workflow — only
  files, config and logging.
- Imports point **downwards only**. `utils` never imports `core`; `core` never
  imports `ui`.
- Long-running work (scanning, decoding, file moves) never blocks the GUI
  thread. See the threading contract in
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#62-threading-model).

`tests/test_architecture.py` enforces the Qt-free rule for `core/` and
`utils/`; keep it green.

---

## Coding standards

- **Python 3.11+**; use modern typing (`list[str]`, `Path`, `X | None`).
- **Formatting:** `ruff format`, line length **100**. It is the only formatter —
  do not add `black`; the two disagree on parenthesized assertions and running
  both makes CI impossible to satisfy.
- **Naming:** `snake_case` for functions, methods, signals and fixtures,
  `PascalCase` for classes, `UPPER_SNAKE` for constants. Qt virtual overrides
  (`paintEvent`, `sizeHint`, …) keep Qt's spelling. `tests/test_architecture.py`
  enforces this, so camelCase helpers fail CI.
- **Linting:** `ruff check .` with the configured rule set (`E`, `F`, `I`, `UP`,
  `B`, `SIM`, `RUF`).
- **Types:** `mypy` in strict mode for `src/image_swiper`. New public functions
  need full annotations, including return types.
- **Docstrings:** every module gets a one-paragraph docstring stating its
  responsibility. Public classes and functions use Google-style docstrings with
  `Args:`, `Returns:` and `Raises:` where relevant.
- **Qt specifics:**
  - Qt objects are created on the GUI thread; workers return plain data.
  - Use `pyqtSignal`/`pyqtSlot` for cross-thread communication, never direct
    widget access from a thread.
  - Prefer signals over callbacks; keep widgets dumb and controllers explicit.
  - No blocking dialogs inside animation or gesture handlers.
- **Filesystem safety:** any code that moves files must be collision-safe and
  must never delete user data. Add a test with `tmp_path` for every new path
  branch (duplicate names, cross-device moves, permission errors).
- **Naming:** modules `snake_case`, classes `PascalCase`, Qt signals in
  `camelCase` to match Qt conventions, constants `UPPER_SNAKE_CASE`.

---

## Tests

```bash
pytest -q                                  # headless unit tests
QT_QPA_PLATFORM=offscreen pytest -q -m gui  # GUI tests (no display needed)
pytest -q --cov=image_swiper --cov-report=term-missing   # coverage (pytest-cov)
sh scripts/build.sh                        # optional: standalone binary, needs network
```

Guidelines:

- Mirror the source tree: `tests/test_sorter.py` tests `core/sorter.py`.
- Use `tmp_path` and the `make_images` fixture from `tests/conftest.py` instead
  of touching the real filesystem.
- GUI tests must be marked `@pytest.mark.gui` and run offscreen in CI; the
  `gui (xvfb)` job runs the same subset again on a virtual X server.
- Bug fixes come with a regression test that fails before the fix.
- `tests/test_packaging.py` is the contract for everything outside `src/`: the
  desktop entry, the icon tree, the install and build scripts, the PyInstaller
  spec, the workflows and the changelog. Extend it when you touch those files —
  the `binary` extra (`pip install ".[binary]"`) is only needed for a real
  PyInstaller build, which CI does in the release workflow.

---

## Commit and pull-request workflow

1. Fork the repo and branch from `main`:
   `feat/swipe-threshold`, `fix/undo-collision`, `docs/install-fedora`.
2. Make focused commits using
   [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(ui): add rotation feedback to swipe widget`.
3. Run the checks before pushing:

   ```bash
   ruff check . && ruff format --check . && mypy && pytest -q
   ```

4. Open a PR that explains **what** changed, **why**, and **how it was tested**
   (screenshots/GIFs for UI changes). Link the issue with `Closes #123`.
5. Keep PRs small. A 400-line PR gets reviewed quickly; a 4 000-line PR does
   not. Refactors and behaviour changes belong in separate PRs.
6. Update the docs when behaviour, configuration keys or shortcuts change, and
   add an `[Unreleased]` entry to [CHANGELOG.md](CHANGELOG.md) for anything a
   user can notice.

A maintainer will review, request changes if needed, and squash-merge.

---

## Pull request checklist

CI enforces the first four; the rest are what a reviewer looks for. The same list
is pre-filled in the [PR template](.github/pull_request_template.md).

- [ ] `ruff check .` — the configured rule set, no `# noqa` without a reason
- [ ] `ruff format --check .` — **not** `black`: the project has exactly one
      formatter, and mixing the two makes CI unsatisfiable
- [ ] `mypy` — strict, over `src/image_swiper`; new public functions are fully
      annotated
- [ ] `pytest -q` — includes `tests/test_architecture.py` (naming and Qt-free
      `core/`+`utils/`) and `tests/test_packaging.py` (artefacts and workflows)
- [ ] GUI changes come with a `@pytest.mark.gui` test and a screenshot/GIF
- [ ] The PR touches one concern; unrelated reformatting is split out
- [ ] Layer boundaries hold: no `PyQt6` import below `ui/`, imports point down
- [ ] File-moving code is collision-safe, never deletes data, and has a test for
      the failure path (duplicate name, cross-device, permission denied)
- [ ] Docs updated: README/`docs/` for behaviour, README shortcut table for keys,
      `docs/CONFIGURATION.md` for new config keys
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry
- [ ] No personal photos, absolute home paths, API tokens or `*.log` files in the
      diff (`screenshots/README.md` explains how to generate demo images)

---

## Reporting bugs

Include:

- ImageSwiper version (`python -c "import image_swiper; print(image_swiper.__version__)"`)
- Distribution and version (`lsb_release -a` or `cat /etc/os-release`)
- Session type (`echo $XDG_SESSION_TYPE`) and desktop environment
- Python and Qt versions (`python -V`,
  `python -c "from PyQt6.QtCore import QT_VERSION_STR; print(QT_VERSION_STR)"`)
- Steps to reproduce, expected vs. actual behaviour
- Relevant log lines from `~/.local/share/image-swiper/logs/image-swiper.log`
  (redact file paths you consider private)

For crashes, a backtrace from `gdb` or the Qt message output is gold.

---

## Licensing of contributions

ImageSwiper is MIT licensed. By submitting a pull request you agree that your
contribution is licensed under the same MIT terms (inbound = outbound). No
CLA is required.

