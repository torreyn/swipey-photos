"""Main application window: the shell that ties the UI to the core layer.

Responsibility
    Provide the frame around the image card and act as the *presenter* of a
    sorting session. ``MainWindow`` owns the session-level state (current
    folder, remaining images, progress counters) and translates user intent
    into core-layer calls. It contains layout and wiring only — no image
    decoding, no file moves, no animation maths.

Composition
    * ``QMainWindow`` with a header (folder path, "12 of 340" progress),
      a :class:`~image_swiper.ui.swipe_widget.SwipeWidget` in the centre,
      and a status bar (last action, error messages, undo hint).
    * A toolbar/menu with *Open folder*, *Undo*, *Rescan*, *Fullscreen*,
      *Shortcuts* and *Quit*.
    * An empty state ("Choose a folder to start") and a completion state
      ("All 340 images sorted" + per-destination counts).

Planned public API
    class MainWindow(QMainWindow):
        open_folder_requested: pyqtSignal()      # user asked for the picker
        sort_requested: pyqtSignal(str)          # card wants to commit; a category
        undo_requested: pyqtSignal()
        def show_image(image: Image.Image, original_size: tuple[int, int]) -> None
        def show_empty_state(message: str) -> None
        def show_error(message: str, detail: str = "") -> None
        def update_progress(done: int, total: int) -> None

Keyboard handling
    Maps ←/A, →/D, ↑/W, ↓/S to the four categories (`Good`, `Bad`, `Great`,
    `OK`), Ctrl+Z to undo,
    Space to skip, Ctrl+O to open, F5/Ctrl+R to rescan, F11 to fullscreen,
    F1/? to the shortcut overlay, Ctrl+Q to quit. Bindings are ``QAction``/
    ``QShortcut`` based so they work regardless of which child widget has focus;
    WASD is ignored while a text input has focus.

Boundary rules
    * Holds references to core objects but never performs I/O itself.
    * Long operations are dispatched to :mod:`image_swiper.ui.workers`; the
      window reacts to their signals on the GUI thread.
    * Persists window size and last folder through
      :mod:`image_swiper.utils.config` on close.

Not implemented yet (milestones M2 and M4).
"""
