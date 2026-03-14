"""Zeroconf-based Bond Bridge discovery."""

from __future__ import annotations

import socket
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


BOND_SERVICE_TYPE = "_bond._tcp.local."
DEFAULT_TIMEOUT_SECONDS = 10


class DiscoveryError(Exception):
    pass


class _BondListener(ServiceListener):
    def __init__(self) -> None:
        self.address: str | None = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if self.address is not None:
            return
        info = zc.get_service_info(type_, name)
        if info and info.addresses:
            self.address = socket.inet_ntoa(info.addresses[0])

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def discover_bridge(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Browse mDNS for a Bond Bridge and return its IP address.

    Raises DiscoveryError if no bridge is found within the timeout.
    """
    zc = Zeroconf()
    listener = _BondListener()
    browser = ServiceBrowser(zc, BOND_SERVICE_TYPE, listener)
    try:
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if listener.address is not None:
                return listener.address
            time.sleep(0.1)
    finally:
        browser.cancel()
        zc.close()

    raise DiscoveryError(
        f"No Bond Bridge found via Zeroconf after {timeout:.0f}s. "
        "Set bond.host in config to skip discovery."
    )
