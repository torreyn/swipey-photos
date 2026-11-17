## What changed

<!-- One paragraph. Link the issue: Closes #123 -->

## Why

<!-- The behaviour that is wrong or missing today. -->

## How it was tested

<!--
  Commands you ran and what they printed, plus a screenshot/GIF for UI changes.
  `ruff check . && ruff format --check . && mypy && pytest -q` is the baseline.
-->

## Checklist

- [ ] Branch is based on `main` and the PR is focused on one change
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes (no `black` — it disagrees with `ruff format`)
- [ ] `mypy` passes (strict, `src/image_swiper`)
- [ ] `pytest -q` passes, and new core logic has tests (`tmp_path`, `make_images`)
- [ ] GUI changes are covered by a `@pytest.mark.gui` test and a screenshot
- [ ] Layer boundaries hold: no PyQt6 import in `core/` or `utils/`
- [ ] Docs updated when behaviour, config keys or shortcuts changed
- [ ] New public functions have type annotations and Google-style docstrings
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry for user-visible changes
- [ ] File-moving code is collision-safe and covered by a failure-path test
