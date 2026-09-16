"""
Shared state for the web demo: one BLE adapter, so an active GATT
connection (sensor reads, notifications) and passive RSSI scanning must
not run at the same time. BLE_LOCK enforces that; whichever side can't
acquire it just reports "paused" this cycle instead of blocking forever.
"""
import asyncio
import time
from dataclasses import dataclass

BLE_LOCK = asyncio.Lock()


@dataclass
class PresenceState:
    rssi: int | None = None
    near: bool = False
    found: bool = False
    last_updated_ts: float = 0.0
    paused: bool = False


presence_state = PresenceState()


def presence_age_seconds() -> float:
    if presence_state.last_updated_ts == 0.0:
        return float("inf")
    return time.time() - presence_state.last_updated_ts
