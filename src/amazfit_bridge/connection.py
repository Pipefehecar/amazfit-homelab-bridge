"""
A persistent, authenticated BleakClient reused across requests, so each
API call doesn't pay the ~15-30s connect+auth handshake cost again.
Reconnects on demand if the link drops.
"""
import asyncio
import logging

from bleak import BleakClient, BleakScanner

from amazfit_bridge.auth import authenticate
from amazfit_bridge.config import WatchConfig

logger = logging.getLogger(__name__)

# The watch only advertises for a few seconds after its screen wakes.
# BleakClient.connect() by MAC alone does NOT actively scan on Linux/BlueZ -
# it only works if BlueZ already knows about the device from some prior
# discovery. So we actively scan for it first (find_device_by_address),
# retrying for a while to give the user a chance to wake the screen.
_CONNECT_RETRY_WINDOW_S = 45.0
_SCAN_ATTEMPT_TIMEOUT_S = 6.0


class WatchConnection:
    def __init__(self, config: WatchConfig):
        self._config = config
        self._client: BleakClient | None = None

    async def ensure_connected(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client

        logger.info("Looking for %s (wake the watch screen if this hangs)...", self._config.mac)
        deadline = asyncio.get_event_loop().time() + _CONNECT_RETRY_WINDOW_S

        device = None
        while device is None:
            device = await BleakScanner.find_device_by_address(
                self._config.mac, timeout=_SCAN_ATTEMPT_TIMEOUT_S
            )
            if device is None:
                if asyncio.get_event_loop().time() >= deadline:
                    raise TimeoutError(
                        f"Watch {self._config.mac} never advertised within "
                        f"{_CONNECT_RETRY_WINDOW_S}s - wake its screen and try again."
                    )
                logger.info("Watch not seen yet - still scanning (wake its screen)...")

        logger.info("Found it. Connecting...")
        client = BleakClient(device)
        await client.connect()

        logger.info("Connected. Authenticating...")
        await authenticate(client, self._config.auth_key)
        logger.info("Auth OK.")

        self._client = client
        return client

    async def close(self) -> None:
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()
        self._client = None
