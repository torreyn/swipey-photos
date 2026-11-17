"""Open a URL in the user's browser with a launcher that reports failures.

Responsibility
    ``QDesktopServices.openUrl`` looks like the obvious tool, but on Wayland
    desktops that route through ``xdg-desktop-portal`` it can return ``True``
    while opening nothing: the About box's *Buy me a coffee* button did exactly
    that, so the click looked like a no-op. This module drives the command-line
    launchers instead, because they exit non-zero when they cannot hand the URL
    on, and it tells the caller when nobody could.

Contains
    browser.py  ``open_in_browser(url)``: ``xdg-open`` → ``gio open`` →
                ``webbrowser``; ``False`` when every launcher refused.

Boundary rules
    * Standard library only: no Qt, no ``core``, no ``ui``.
    * Never raises because a launcher is missing or refuses the URL; the next
      candidate gets a turn, and ``False`` means "nothing could open it".
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import webbrowser

LOGGER = logging.getLogger(__name__)

#: Seconds to wait for a launcher before assuming it is running the browser in
#: the foreground (``xdg-open`` blocks that way on some desktops) and worked.
LAUNCH_TIMEOUT = 5.0

#: Launchers tried in order; each receives the URL as its final argument.
LAUNCHERS: tuple[tuple[str, ...], ...] = (("xdg-open",), ("gio", "open"))

#: Launchers that outlived :data:`LAUNCH_TIMEOUT`. Holding on to the process
#: objects keeps ``Popen`` from complaining about a child that is still alive.
_LINGERING: list[subprocess.Popen[bytes]] = []


def open_in_browser(url: str) -> bool:
    """Open *url* in the desktop's default browser.

    Args:
        url: Absolute URL, such as ``https://example.com``.

    Returns:
        True when a launcher took the URL, False when every candidate failed;
        the caller should then show *url* so it can be opened by hand.
    """
    for command in LAUNCHERS:
        if shutil.which(command[0]) is None:
            LOGGER.debug("%s is not installed; trying the next launcher", command[0])
            continue
        if _launch([*command, url]):
            LOGGER.info("opened %s with %s", url, command[0])
            return True
    return _open_with_webbrowser(url)


def _launch(command: list[str]) -> bool:
    """Run *command*, returning True when it accepted the URL."""
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # Detach, so a browser started this way survives Ctrl+C in whatever
            # terminal happened to launch it.
            start_new_session=True,
        )
    except OSError as exc:  # missing binary, no permission, out of fds, …
        LOGGER.debug("could not run %s: %s", command[0], exc)
        return False
    try:
        return process.wait(timeout=LAUNCH_TIMEOUT) == 0
    except subprocess.TimeoutExpired:
        LOGGER.debug("%s still running after %ss; assuming it worked", command[0], LAUNCH_TIMEOUT)
        _LINGERING.append(process)
        return True


def _open_with_webbrowser(url: str) -> bool:
    """Last resort: let :mod:`webbrowser` pick a browser itself."""
    try:
        opened = webbrowser.open(url)
    except (webbrowser.Error, OSError) as exc:
        LOGGER.debug("webbrowser could not open %s: %s", url, exc)
        return False
    if not opened:
        LOGGER.warning("no launcher could open %s", url)
    return opened
