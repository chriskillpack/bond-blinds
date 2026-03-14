"""Zeroconf-based Bond Bridge discovery."""

from __future__ import annotations

import socket
import time
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


BOND_SERVICE_TYPE = "_bond._tcp.local."
DEFAULT_TIMEOUT_SECONDS = 10


class DiscoveryError(Exception):
    pass


class _BondListener(ServiceListener):
    def __init__(self, name_filter: str | None = None) -> None:
        # Optional case-insensitive name to match against the mDNS service name.
        self._name_filter = name_filter.lower() if name_filter else None
        self.address: str | None = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if self.address is not None:
            return
        if self._name_filter is not None:
            # mDNS name is e.g. "BD12345._bond._tcp.local." — strip the service type suffix.
            service_name = name.removesuffix("." + type_).removesuffix(type_).lower()
            if self._name_filter != service_name:
                return
        info = zc.get_service_info(type_, name)
        if info and info.addresses:
            self.address = socket.inet_ntoa(info.addresses[0])

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass


def discover_bridge(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    name: str | None = None,
) -> str:
    """Browse mDNS for a Bond Bridge and return its IP address.

    If name is given, only a bridge whose mDNS service name matches (case-insensitive)
    will be returned. Raises DiscoveryError if no matching bridge is found within timeout.
    """
    zc = Zeroconf()
    listener = _BondListener(name_filter=name)
    browser = ServiceBrowser(zc, BOND_SERVICE_TYPE, listener)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if listener.address is not None:
                return listener.address
            time.sleep(0.1)
    finally:
        browser.cancel()
        zc.close()

    if name:
        raise DiscoveryError(
            f"No Bond Bridge named {name!r} found via Zeroconf after {timeout:.0f}s. "
            "Check the name or set bond.host in config to skip discovery."
        )
    raise DiscoveryError(
        f"No Bond Bridge found via Zeroconf after {timeout:.0f}s. "
        "Set bond.host in config to skip discovery."
    )
