"""Synchronous HTTP client for the Bond Local API v2."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx


logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10.0  # seconds; Bond API docs state actions can block up to 7s


@dataclass
class DeviceInfo:
    id: str
    name: str
    type: str
    actions: list[str]


class BondClient:
    def __init__(self, host: str, token: str) -> None:
        self._base_url = f"http://{host}/v2"
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"BOND-Token": token},
            timeout=REQUEST_TIMEOUT,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BondClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def get_version(self) -> dict:
        """GET /v2/sys/version — health check, returns firmware info."""
        resp = self._client.get("/sys/version")
        resp.raise_for_status()
        data = resp.json()
        logger.debug("version response: %s", data)
        return data

    def list_devices(self) -> list[str]:
        """GET /v2/devices — returns list of device ID strings."""
        resp = self._client.get("/devices")
        resp.raise_for_status()
        data = resp.json()
        logger.debug("list_devices response: %s", data)
        # Response is a dict of {id: {}} plus a "_" key; filter out underscore keys.
        return [k for k in data if not k.startswith("_")]

    def get_device(self, device_id: str) -> DeviceInfo:
        """GET /v2/devices/{id} — returns device detail."""
        resp = self._client.get(f"/devices/{device_id}")
        resp.raise_for_status()
        data = resp.json()
        logger.debug("get_device %s response: %s", device_id, data)
        actions = list(data.get("actions", []))
        return DeviceInfo(
            id=device_id,
            name=data.get("name", device_id),
            type=data.get("type", ""),
            actions=actions,
        )

    def execute_action(self, device_id: str, action: str) -> int:
        """PUT /v2/devices/{id}/actions/{action} — send Open or Close.

        Returns the HTTP status code. Logs and returns the status on error
        rather than raising, so a single failure doesn't abort a retry round.
        """
        try:
            resp = self._client.put(
                f"/devices/{device_id}/actions/{action}",
                json={},
            )
            logger.debug(
                "execute_action %s %s -> %s", device_id, action, resp.status_code
            )
            return resp.status_code
        except httpx.TimeoutException as exc:
            logger.warning(
                "Timeout sending %s to device %s: %s", action, device_id, exc
            )
            return 0
        except httpx.RequestError as exc:
            logger.warning(
                "Request error sending %s to device %s: %s", action, device_id, exc
            )
            return 0
