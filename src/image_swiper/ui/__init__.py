"""Qt presentation layer.

Responsibility
    Everything the user sees and touches: the main window shell, the swipeable
    image card, animation choreography, keyboard bindings and the background
    worker adapters that keep the GUI thread responsive.

Contains
    main_window.py   MainWindow: menus, toolbar, status bar, session wiring.
    swipe_widget.py  SwipeWidget: renders the current image, tracks the drag,
                     resolves it into a category and paints feedback.
    animator.py      CardAnimator: fly-out, fly-in and spring-back animations.
    workers.py       QRunnable/QObject adapters that call synchronous core
                     functions on a QThreadPool and deliver results via signals.

Boundary rules
    * This package (together with :mod:`image_swiper.app`) is the only place
      allowed to import ``PyQt6``. ``core`` and ``utils`` stay Qt-free so they
      can be unit tested headlessly and reused by a future CLI.
    * Widgets never touch the filesystem; they emit signals and let the main
      window delegate to the core layer.
    * Core data objects are converted to Qt types (``QPixmap``/``QImage``) at
      this boundary, on the GUI thread.

See ``docs/ARCHITECTURE.md`` for the state machines and signal contract.
"""
