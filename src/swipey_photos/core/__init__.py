"""Toolkit-agnostic domain layer: scanning, decoding and sorting images.

Responsibility
    Implement the actual work of the application in plain Python (plus Pillow),
    with no Qt imports and no knowledge of widgets. Every function here is
    synchronous, typed and testable on its own; the UI layer decides *when* to
    call it and on which thread.

Contains
    image_loader.py   Scan a folder, validate files with Pillow, provide
                      downscaled previews and prefetch candidates.
    sorter.py         Own the queue cursor, move the current image into a
                      category through ``FolderManager``, keep the undo stack.
    folder_manager.py Create the four category folders, validate category names
                      and perform collision-free moves through ``utils.file_ops``.

Boundary rules
    * ``core`` may import ``utils``; never ``ui`` and never ``PyQt6``.
    * No blocking dialogs, no global state, no direct ``print`` — callers decide
      how to surface errors.
    * Functions accept and return ``pathlib.Path`` and small frozen dataclasses;
      nothing here knows about ``QImage``.

See ``docs/ARCHITECTURE.md`` for contracts and error-handling rules.
"""
