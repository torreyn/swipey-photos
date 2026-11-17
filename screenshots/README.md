# Screenshots

Reference images for `README.md` and the docs live here. This folder is a
convention, not a gallery: only shots that a document references belong in it.

## What is here now

Nothing yet — the README links a placeholder mock-up
([`docs/assets/screenshot-main.svg`](../docs/assets/screenshot-main.svg)) until
the first real capture lands. Drop the files below in and they can be linked from
the README's *Screenshots* section.

| File | Shows | Suggested size |
| --- | --- | --- |
| `main-window.png` | the stage: header counts, card, caption, arrow-labelled footer, summary bar | 1100 × 780 |
| `drag-feedback.png` | a card mid-drag: rotation, tinted background, direction badge | 1100 × 780 |
| `summary.png` | the completion page after a folder is drained | 1100 × 780 |
| `welcome.png` | the welcome page with the recent-folder list | 1100 × 780 |

## How to capture them

The app renders under Qt's `offscreen` platform plugin, so a real display, a
window manager or a screenshot tool is not needed: `QWidget.grab()` returns the
painted pixels. From the repository root, with the dev extra installed
(`pip install -e ".[dev]"`):

```bash
QT_QPA_PLATFORM=offscreen FOLDER=~/Pictures/unsorted \
  python - <<'PY'
import os
import sys
import time
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from swipey_photos.ui.main_window import MainWindow

folder = Path(os.environ["FOLDER"]).expanduser()
out = Path(os.environ.get("OUT", "screenshots/main-window.png"))

app = QApplication(sys.argv[:1])
window = MainWindow()
window.resize(1100, 780)
window.show()
window.open_folder(folder)

# Let the prefetch workers deliver the first pixmap and the fade-in finish;
# a grab taken too early catches an empty card.
deadline = time.monotonic() + 1.0
while time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.02)

out.parent.mkdir(parents=True, exist_ok=True)
window.grab().save(str(out))
print(f"wrote {out} ({window.width()}x{window.height()})")
PY
```

Notes:

- **Use a throwaway folder.** Point `FOLDER` at a copy of some images, never at
  a library you care about: `open_folder()` is the ordinary entry point, but the
  card only *displays* images until you swipe. `--dry-run` equivalents do not
  exist for a scripted session, so keep it to a copy and press nothing.
- **Keep personal photos out of the repository.** Generate test images with
  Pillow (`Image.new("RGB", (1600, 1200), colour)`), or reuse the `make_images`
  fixture from [`tests/conftest.py`](../tests/conftest.py).
- **Same window size for every shot**, so the images line up in a table. 1100 ×
  780 is what the README placeholders assume.
- **PNG only, ideally under ~400 KB.** Qt writes PNG with `save()`; convert with
  `optipng` or `pngquant` if a shot is heavier than that.
- For `drag-feedback.png`, run the snippet, then drive the drag before grabbing:
  `window.swipe_widget.card` exposes the card, and a `QTest.mousePress` /
  `QTest.mouseMove` sequence reproduces the tilt and tint (see the gesture
  helpers in [`tests/test_swipe_card.py`](../tests/test_swipe_card.py)).
- For `summary.png`, sort every image in a **copy** first and grab afterwards —
  the completion page appears on its own once the deck is empty:

  ```python
  while window.current_page == "stage":
      window.category_buttons["Good"].click()
      app.processEvents()
  ```


## Refreshing the README

After adding a file, link it from the *Screenshots* section of `README.md`:

```markdown
![Swipey Photos main window](screenshots/main-window.png)
```

Keep the alt text descriptive — it is what a screen reader announces and what
GitHub shows while the image loads.
