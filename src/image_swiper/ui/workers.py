"""Background worker adapters between Qt and the synchronous core layer.

Responsibility
    Bridge the GUI thread and :mod:`image_swiper.core`. Core functions are
    deliberately synchronous and Qt-free; this module wraps them in ``QRunnable``
    objects (``ScanWorker``, ``PreviewWorker``, ``MoveWorker``) that run on a
    shared ``QThreadPool`` and report results through a signals object.

Planned public API
    class WorkerSignals(QObject):
        finished: pyqtSignal(object)       # payload of the completed job
        failed: pyqtSignal(str, str)       # human message, traceback/detail
        progress: pyqtSignal(int, int)     # done, total (scan only)

    class ScanWorker(QRunnable):
        Runs ImageLoader.scan_folder() off the GUI thread.

    class PreviewWorker(QRunnable):
        Decodes and downscales one image for display.

    class MoveWorker(QRunnable):
        Asks the Sorter to move one file; emits the MoveRecord.

Threading contract
    * Workers receive only plain data (``Path``, ints, frozen dataclasses) and
      never hold a reference to a widget.
    * Results are delivered as Qt signals, which are queued onto the GUI
      thread; conversion to ``QPixmap`` happens in the slot, not the worker.
    * Workers are fire-and-forget ``QRunnable`` instances auto-managed by the
      thread pool; cancellation is cooperative via a shared ``threading.Event``.
    * Exceptions must never escape ``run()``: catch, log, emit ``failed``.
    * The pool size is bounded (e.g. ``max(1, cpu_count - 1)``) so a huge folder
      cannot saturate the machine.

Not implemented yet (planned; scanning, decoding and moves run on the GUI thread today).
"""
