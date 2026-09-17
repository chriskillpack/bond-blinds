"""Tests for the daemon's bridge connection retry."""

from __future__ import annotations

import pytest

from bond_blinds import daemon


class _FlakyBridge:
    """Fails get_version the first `failures` times, then answers."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def get_version(self) -> dict:
        self.calls += 1
        if self.calls <= self.failures:
            raise OSError(65, "No route to host")
        return {"fw_ver": "v4.37.40", "model": "BD-1000"}


@pytest.fixture
def delays(monkeypatch) -> list[float]:
    """Record the backoff delays instead of actually sleeping."""
    recorded: list[float] = []
    monkeypatch.setattr(daemon, "_sleep_for", recorded.append)
    monkeypatch.setattr(daemon, "_running", True)
    return recorded


def test_connect_returns_the_version_without_sleeping(delays):
    version = daemon._connect(_FlakyBridge(failures=0), "192.168.4.13")

    assert version["model"] == "BD-1000"
    assert delays == []


def test_connect_retries_until_the_bridge_answers(delays):
    bridge = _FlakyBridge(failures=3)

    version = daemon._connect(bridge, "192.168.4.13")

    assert version["fw_ver"] == "v4.37.40"
    assert bridge.calls == 4


def test_connect_backs_off_exponentially(delays):
    daemon._connect(_FlakyBridge(failures=4), "192.168.4.13")

    assert delays == [5.0, 10.0, 20.0, 40.0]


def test_connect_caps_the_backoff(delays):
    daemon._connect(_FlakyBridge(failures=10), "192.168.4.13")

    assert delays[-1] == daemon.CONNECT_RETRY_MAX
    assert delays == sorted(delays)


def test_connect_stops_when_the_daemon_is_shutting_down(monkeypatch):
    # A SIGTERM arriving during a backoff sleep must end the loop rather than
    # leave launchd waiting out a five minute retry.
    monkeypatch.setattr(daemon, "_running", True)
    monkeypatch.setattr(
        daemon, "_sleep_for", lambda _: monkeypatch.setattr(daemon, "_running", False)
    )

    assert daemon._connect(_FlakyBridge(failures=99), "192.168.4.13") is None
