"""Qt presentation layer.

Responsibility
    Everything the user sees and touches: the main window shell, the welcome and
    completion pages, the swipeable image card, animation choreography, keyboard
    bindings and the background worker adapters that keep the GUI thread
    responsive.

Contains
    main_window.py      MainWindow: menus, status bar with the live per-category
                        summary, session wiring, the three-page flow
                        (welcome → stage → summary) and the --dry-run mode.
    welcome_screen.py   WelcomeScreen: "Select Folder" empty state plus the five
                        most recent folders.
    completion_screen.py CompletionScreen: per-category summary with restart,
                        pick-another-folder and quit actions.
    shortcut_overlay.py ShortcutOverlay: the F1/? reference grid of every
                        keyboard binding, built from one table.
    swipe_card.py       SwipeCard: renders one image, owns the drag/rotation
                        maths, paints the feedback badge, flies itself out.
    swipe_widget.py     SwipeWidget/CardStage: the stage that hosts the card,
                        feeds it pixmaps, shows the gesture legend and forwards
                        committed categories.
    animator.py         CardAnimator: deck-level choreography (150 ms card
                        entrance fade/slide) and the shared timing/easing
                        policy.
    workers.py          PreviewPrefetcher/PreviewWorker: decode upcoming previews
                        on a bounded QThreadPool and hand them back as QImages.
    image_utils.py      Pillow → QImage/QPixmap conversion, the only bridge
                        between the decoded core data and Qt.
    theme.py            Light/dark palettes plus the system-preference lookup
                        behind View → Dark Mode.
    branding.py         Generated window icon and welcome logo (no asset files).

Boundary rules
    * This package (together with :mod:`image_swiper.app`) is the only place
      allowed to import ``PyQt6``. ``core`` and ``utils`` stay Qt-free so they
      can be unit tested headlessly and reused by a future CLI.
    * Widgets never touch the filesystem; they emit signals and let the main
      window delegate to the core layer.
    * Core data objects are converted to Qt types (``QPixmap``/``QImage``) at
      this boundary, on the GUI thread, through :mod:`image_swiper.ui.image_utils`.

See ``docs/ARCHITECTURE.md`` for the state machines and signal contract.
"""
