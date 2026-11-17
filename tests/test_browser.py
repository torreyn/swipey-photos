"""Tests for ``utils/browser.py``: launcher selection and failure reporting.

Coverage
    * ``xdg-open`` is preferred; ``gio open`` and :mod:`webbrowser` only run when
      the candidates before them are missing or refuse the URL;
    * a launcher still running after ``LAUNCH_TIMEOUT`` counts as a success,
      because ``xdg-open`` runs the browser in the foreground on some desktops;
    * a desktop where nothing accepts the URL returns ``False`` instead of
      raising, so the window can show the URL to the user.

Conventions
    * No process is ever started: ``subprocess``, ``shutil`` and ``webbrowser``
      are replaced by recorders, and ``_LINGERING`` is a per-test list.
"""

from __future__ import annotations

import subprocess
import webbrowser
from types import SimpleNamespace

import pytest

from swipey_photos.utils import browser

URL = "https://example.com/support"


class FakeProcess:
    """``subprocess.Popen`` stand-in with a scripted exit status."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


class HangingProcess(FakeProcess):
    """Launcher that never exits, as when it runs the browser in the foreground."""

    def wait(self, timeout: float | None = None) -> int:
        raise subprocess.TimeoutExpired(cmd="launcher", timeout=timeout or 0)


class Recorder:
    """Records what ``utils.browser`` tries and answers for it."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.results: dict[str, FakeProcess] = {}
        self.installed: set[str] = {"xdg-open", "gio"}
        self.vanished: set[str] = set()
        self.webbrowser_urls: list[str] = []
        self.webbrowser_result = False

    def popen(self, command: list[str], **_kwargs: object) -> FakeProcess:
        self.commands.append(command)
        if command[0] in self.vanished:
            raise OSError(2, "No such file or directory")
        return self.results.get(command[0], FakeProcess())

    def which(self, name: str) -> str | None:
        return f"/usr/bin/{name}" if name in self.installed else None

    def open_url(self, url: str) -> bool:
        self.webbrowser_urls.append(url)
        return self.webbrowser_result


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Replace every launcher with a recorder for the duration of a test."""
    fake = Recorder()
    monkeypatch.setattr(
        browser,
        "subprocess",
        SimpleNamespace(
            DEVNULL=subprocess.DEVNULL,
            TimeoutExpired=subprocess.TimeoutExpired,
            Popen=fake.popen,
        ),
    )
    monkeypatch.setattr(browser, "shutil", SimpleNamespace(which=fake.which))
    monkeypatch.setattr(
        browser,
        "webbrowser",
        SimpleNamespace(open=fake.open_url, Error=webbrowser.Error),
    )
    monkeypatch.setattr(browser, "_LINGERING", [])
    return fake


def test_opens_the_url_with_xdg_open(recorder: Recorder) -> None:
    """``xdg-open`` is the first choice and gets the URL as its only argument."""
    assert browser.open_in_browser(URL) is True

    assert recorder.commands == [["xdg-open", URL]]
    assert recorder.webbrowser_urls == []


def test_skips_a_launcher_that_is_not_installed(recorder: Recorder) -> None:
    """A missing ``xdg-open`` hands over to ``gio open`` without an error."""
    recorder.installed.discard("xdg-open")

    assert browser.open_in_browser(URL) is True

    assert recorder.commands == [["gio", "open", URL]]


def test_falls_through_to_gio_when_xdg_open_fails(recorder: Recorder) -> None:
    """A non-zero exit status means "try the next launcher", not "give up"."""
    recorder.results["xdg-open"] = FakeProcess(returncode=3)

    assert browser.open_in_browser(URL) is True

    assert recorder.commands == [["xdg-open", URL], ["gio", "open", URL]]


def test_survives_a_launcher_that_vanishes_before_exec(recorder: Recorder) -> None:
    """An ``OSError`` from ``Popen`` is treated like "not installed"."""
    recorder.vanished.add("xdg-open")

    assert browser.open_in_browser(URL) is True

    assert recorder.commands == [["xdg-open", URL], ["gio", "open", URL]]


def test_falls_back_to_the_webbrowser_module(recorder: Recorder) -> None:
    """With no working launcher, the standard library gets the last turn."""
    recorder.results["xdg-open"] = FakeProcess(returncode=3)
    recorder.results["gio"] = FakeProcess(returncode=1)
    recorder.webbrowser_result = True

    assert browser.open_in_browser(URL) is True

    assert recorder.webbrowser_urls == [URL]


def test_reports_failure_when_nothing_can_open_the_url(recorder: Recorder) -> None:
    """A desktop with no launcher returns ``False`` so the caller can help."""
    recorder.installed.clear()

    assert browser.open_in_browser(URL) is False

    assert recorder.commands == []
    assert recorder.webbrowser_urls == [URL]


def test_a_launcher_that_keeps_running_counts_as_success(recorder: Recorder) -> None:
    """A foreground browser outliving the timeout is a success, and is retained."""
    recorder.results["xdg-open"] = HangingProcess()

    assert browser.open_in_browser(URL) is True

    assert recorder.commands == [["xdg-open", URL]]
    assert len(browser._LINGERING) == 1


def test_survives_a_webbrowser_module_without_a_browser(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A :mod:`webbrowser` that raises is a failure, not a crash."""
    recorder.installed.clear()

    def explode(_url: str) -> bool:
        raise webbrowser.Error("could not locate runnable browser")

    monkeypatch.setattr(
        browser,
        "webbrowser",
        SimpleNamespace(open=explode, Error=webbrowser.Error),
    )

    assert browser.open_in_browser(URL) is False
