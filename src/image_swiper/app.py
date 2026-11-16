"""Application bootstrap and object wiring.

Responsibility
    Own the process-level lifecycle: create the ``QApplication``, apply the
    application name/version/icon and style hints, build the configured
    dependencies (config, logger, image loader, sorter, folder manager), create
    :class:`image_swiper.ui.main_window.MainWindow`, and run the Qt event loop.

This module is the *composition root*. It is the only place where concrete
implementations from ``core`` and ``utils`` are instantiated and handed to the
UI, which keeps widgets testable with fakes and keeps ``core`` free of Qt.

Planned public API
    run(argv: list[str] | None = None, config: Config | None = None) -> int
        Configure the process, show the main window, and return the Qt exit
        code. Called by :func:`image_swiper.__main__.main`.
    build_main_window(app: QApplication, config: Config) -> MainWindow
        Construct the dependency graph without entering the event loop; used by
        integration tests.

Rules
    * All ``QApplication`` construction and ``sys.exit`` handling lives here.
    * No filesystem scanning, decoding or file moves happen in this module.
    * Importing this module must not create widgets or touch ``sys.argv``.

Not implemented yet (milestone M1).
"""
