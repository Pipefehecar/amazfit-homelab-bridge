"""
Passive BLE presence detection: scan for advertisements from the watch's
MAC and report RSSI, without connecting. EXPERIMENTAL - first pass.

Note (see project history): this watch only advertises for a few seconds
after its screen wakes, not continuously - so "not found" does not
necessarily mean "far away", it can just mean the screen is asleep.
Treat the presence signal as best-effort, not authoritative.

`escanear_continuo` (used by web.py) keeps a BleakScanner running instead
of doing start/stop bursts every cycle — bursts had a blind window
between them (the previous demo scanned 4s out of every 6s) where any
advertisement was silently missed. Continuous scanning only misses an
advertisement if it lands exactly while BLE_LOCK is held for a GATT op.
"""
import asyncio
import logging
import time
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

    Kept for the one-shot /presence demo call; the always-on presence
    loop uses `escanear_continuo` instead.
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
        await asyncio.sleep(timeout)
    finally:
        await scanner.stop()

    if best_rssi is None:
        logger.info("Presence scan: watch not seen this burst")
        return PresenceReading(found=False, rssi=None, near=False)

    near = best_rssi >= near_threshold_dbm
    logger.info("Presence scan: rssi=%d near=%s (threshold=%d)", best_rssi, near, near_threshold_dbm)
    return PresenceReading(found=True, rssi=best_rssi, near=near)


async def escanear_continuo(target_mac: str, presence_state, ble_lock, chequeo_lock_s: float = 1.0) -> None:
    """
    Escaneo BLE de fondo, sin cortes. Actualiza `presence_state` en cada
    anuncio real del reloj (no en un ciclo fijo), así `last_updated_ts`
    pasa a significar "hace cuánto se vio de verdad al reloj" en vez de
    "hace cuánto corrió el último ciclo de scan" — eso es lo que permite
    decidir presencia por antigüedad de la lectura en vez de por una
    racha de ciclos de sondeo.

    Se detiene solo mientras BLE_LOCK está tomado por una operación GATT
    (un adaptador no puede escanear y conectar a la vez) y retoma apenas
    se libera.
    """
    target_mac = target_mac.upper()
    scanner: BleakScanner | None = None

    def on_detect(device, adv_data) -> None:
        if device.address.upper() != target_mac:
            return
        presence_state.rssi = adv_data.rssi
        presence_state.found = True
        presence_state.near = adv_data.rssi >= presence_state.near_threshold_dbm
        presence_state.last_updated_ts = time.time()

    logger.info("Escaneo de presencia continuo arrancado para %s", target_mac)
    try:
        while True:
            if ble_lock.locked():
                presence_state.paused = True
                if scanner is not None:
                    await scanner.stop()
                    scanner = None
                await asyncio.sleep(chequeo_lock_s)
                continue

            presence_state.paused = False
            if scanner is None:
                scanner = BleakScanner(detection_callback=on_detect)
                await scanner.start()
            await asyncio.sleep(chequeo_lock_s)
    finally:
        if scanner is not None:
            await scanner.stop()
