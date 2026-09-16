"""
Read individual sensor values from the watch over an already-authenticated
BleakClient connection (call amazfit_bridge.auth.authenticate first).

Each function is self-contained, logs the characteristic UUID it touches
and the raw payload it receives, and returns both a parsed value and the
raw bytes so misinterpretation can be spotted by comparing against the
watch's own screen.

UUID reference (classic Huami protocol, service 0000fee0):
    00000006-0000-3512-2118-0009af100700  Battery
    00000007-0000-3512-2118-0009af100700  Realtime steps / activity
Standard BLE Heart Rate service (0000180d):
    00002a37-...  Heart Rate Measurement (notify)
    00002a39-...  Heart Rate Control Point (write)

Stress score and sleep phases are NOT exposed as simple readable
characteristics on this device. On the classic Huami protocol they are
retrieved through the binary "activity fetch" log protocol (characteristics
00000004/00000005 under fee0), which streams historical records rather than
a single current value. That's a separate, more involved protocol to
implement — see read_activity_log() stub below for what's needed next.
"""
import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakClient

logger = logging.getLogger(__name__)

BATTERY_CHAR = "00000006-0000-3512-2118-0009af100700"
STEPS_CHAR = "00000007-0000-3512-2118-0009af100700"
HR_MEASUREMENT_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"
HR_CONTROL_POINT_CHAR = "00002a39-0000-1000-8000-00805f9b34fb"


@dataclass
class BatteryStatus:
    level_percent: int
    status_byte: int
    raw: bytes


@dataclass
class StepsStatus:
    steps: int
    distance_m: int
    calories: int
    raw: bytes


async def read_battery(client: BleakClient) -> BatteryStatus:
    logger.info("Reading battery from %s", BATTERY_CHAR)
    raw = bytes(await client.read_gatt_char(BATTERY_CHAR))
    logger.info("Battery raw payload: %s", raw.hex())

    # raw[0] is a packet-type marker (observed 0x0f), not the level.
    # Confirmed against the watch's own battery reading (57%).
    level = raw[1] if len(raw) > 1 else 0
    status_byte = raw[8] if len(raw) > 8 else 0

    return BatteryStatus(level_percent=level, status_byte=status_byte, raw=raw)


async def read_steps_today(client: BleakClient) -> StepsStatus:
    logger.info("Reading steps from %s", STEPS_CHAR)
    raw = bytes(await client.read_gatt_char(STEPS_CHAR))
    logger.info("Steps raw payload: %s", raw.hex())

    # raw[0] is a packet-type marker (observed 0x0c), then three uint32 LE
    # fields: steps, distance_m, calories. Confirmed against watch (~45 steps
    # after a recent reset matched the user's estimate).
    steps = int.from_bytes(raw[1:5], byteorder="little") if len(raw) >= 5 else 0
    distance_m = int.from_bytes(raw[5:9], byteorder="little") if len(raw) >= 9 else 0
    calories = int.from_bytes(raw[9:13], byteorder="little") if len(raw) >= 13 else 0

    return StepsStatus(steps=steps, distance_m=distance_m, calories=calories, raw=raw)


async def read_hr_once(client: BleakClient, timeout: float = 30.0) -> int:
    """
    Trigger a single manual heart-rate measurement and wait for the
    resulting notification on the standard Heart Rate Measurement char.
    Sequence per the classic Huami HR control point protocol:
        stop any ongoing measurement -> disable continuous -> start manual.
    """
    logger.info("Requesting single HR reading via %s", HR_CONTROL_POINT_CHAR)

    result: dict = {}
    got_reading = asyncio.Event()

    def on_hr_notify(_, data: bytearray) -> None:
        raw = bytes(data)
        logger.info("HR notify raw payload: %s", raw.hex())
        result["raw"] = raw
        result["bpm"] = _parse_hr_measurement(raw)
        got_reading.set()

    await client.start_notify(HR_MEASUREMENT_CHAR, on_hr_notify)
    try:
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x02, 0x00]))
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x01, 0x00]))
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x02, 0x01]))

        await asyncio.wait_for(got_reading.wait(), timeout=timeout)
    finally:
        await client.stop_notify(HR_MEASUREMENT_CHAR)

    return result["bpm"]


async def subscribe_hr_continuous(client: BleakClient, duration: float = 60.0) -> list[int]:
    """
    Enable continuous HR mode and collect BPM readings as they arrive for
    `duration` seconds. Returns the list of readings (raw payloads are
    logged as they come in).
    """
    logger.info("Enabling continuous HR mode via %s", HR_CONTROL_POINT_CHAR)

    readings: list[int] = []

    def on_hr_notify(_, data: bytearray) -> None:
        raw = bytes(data)
        logger.info("HR notify raw payload: %s", raw.hex())
        bpm = _parse_hr_measurement(raw)
        readings.append(bpm)

    await client.start_notify(HR_MEASUREMENT_CHAR, on_hr_notify)
    try:
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x01, 0x00]))
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x01, 0x01]))
        await asyncio.sleep(duration)
    finally:
        await client.write_gatt_char(HR_CONTROL_POINT_CHAR, bytes([0x15, 0x01, 0x00]))
        await client.stop_notify(HR_MEASUREMENT_CHAR)

    return readings


def _parse_hr_measurement(raw: bytes) -> int:
    """Standard Bluetooth SIG Heart Rate Measurement (0x2A37) parsing."""
    if not raw:
        return 0
    flags = raw[0]
    hr_format_is_uint16 = flags & 0x01
    if hr_format_is_uint16:
        return int.from_bytes(raw[1:3], byteorder="little")
    return raw[1] if len(raw) > 1 else 0


async def read_activity_log(client: BleakClient):
    """
    Placeholder: sleep phases and stress score aren't exposed as a single
    readable/notify characteristic on this device. They live in the
    historical activity log, fetched via a multi-step binary protocol over
    00000004 (fetch control) / 00000005 (activity data) under fee0 -
    the watch streams records in chunks after you request a time range.
    Not implemented yet - needs its own reverse-engineering pass.
    """
    raise NotImplementedError(
        "Stress/sleep data requires the activity-fetch log protocol "
        "(00000004/00000005 chars) - not a simple read. See docstring."
    )
