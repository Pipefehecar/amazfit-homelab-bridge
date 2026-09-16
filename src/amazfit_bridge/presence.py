"""
Passive BLE presence detection: scan for advertisements from the watch's
MAC and report RSSI, without connecting. EXPERIMENTAL - first pass.

Note (see project history): this watch only advertises for a few seconds
after its screen wakes, not continuously - so a "not found" scan burst
does not necessarily mean "far away", it can just mean the screen is
asleep. Treat the presence signal as best-effort, not authoritative.
"""
import logging
from dataclasses import dataclass

from bleak import BleakScanner

logger = logging.getLogger(__name__)


@dataclass
class PresenceReading:
    found: bool
    rssi: int | None
    near: bool


async def scan_for_rssi(target_mac: str, near_threshold_dbm: int, timeout: float = 4.0) -> PresenceReading:
    """
    One passive scan burst. Returns the strongest RSSI seen for target_mac
    during the window, or found=False if it never advertised.
    """
    target_mac = target_mac.upper()
    logger.info("Presence scan burst (%.1fs) for %s", timeout, target_mac)

    best_rssi: int | None = None

    def on_detect(device, adv_data) -> None:
        nonlocal best_rssi
        if device.address.upper() == target_mac:
            if best_rssi is None or adv_data.rssi > best_rssi:
                best_rssi = adv_data.rssi

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        import asyncio

        await asyncio.sleep(timeout)
    finally:
        await scanner.stop()

    if best_rssi is None:
        logger.info("Presence scan: watch not seen this burst")
        return PresenceReading(found=False, rssi=None, near=False)

    near = best_rssi >= near_threshold_dbm
    logger.info("Presence scan: rssi=%d near=%s (threshold=%d)", best_rssi, near, near_threshold_dbm)
    return PresenceReading(found=True, rssi=best_rssi, near=near)
