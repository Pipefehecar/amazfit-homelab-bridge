"""
A persistent, authenticated BleakClient reused across requests, so each
API call doesn't pay the ~15-30s connect+auth handshake cost again.
Reconnects on demand if the link drops.
"""
import logging

from bleak import BleakClient

from amazfit_bridge.auth import authenticate
from amazfit_bridge.config import WatchConfig

logger = logging.getLogger(__name__)


class WatchConnection:
    def __init__(self, config: WatchConfig):
        self._config = config
        self._client: BleakClient | None = None

    async def ensure_connected(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client

        logger.info("Connecting to %s ...", self._config.mac)
        client = BleakClient(self._config.mac)
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
