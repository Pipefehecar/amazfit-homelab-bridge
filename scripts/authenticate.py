"""
Perform the Huami BLE auth handshake against the watch, then read a couple
of previously-locked characteristics to confirm it worked.

Usage:
    python scripts/authenticate.py
"""
import asyncio

from bleak import BleakClient

from amazfit_bridge.auth import authenticate
from amazfit_bridge.config import load_watch_config

# fee1 characteristics that returned empty before auth
BATTERY_CHAR = "0000fedd-0000-1000-8000-00805f9b34fb"  # write - request battery
HR_MEASUREMENT_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"


async def main() -> None:
    cfg = load_watch_config()
    print(f"Connecting to {cfg.mac} ...")

    async with BleakClient(cfg.mac) as client:
        print("Connected. Authenticating...")
        await authenticate(client, cfg.auth_key)
        print("Auth handshake succeeded.\n")

        print("Reading previously-locked fee1 characteristics:")
        for uuid in [
            "0000fed0-0000-1000-8000-00805f9b34fb",
            "0000fed1-0000-1000-8000-00805f9b34fb",
            "0000fed2-0000-1000-8000-00805f9b34fb",
            "0000fed3-0000-1000-8000-00805f9b34fb",
        ]:
            try:
                value = await client.read_gatt_char(uuid)
                print(f"  {uuid}: {value.hex()}")
            except Exception as exc:
                print(f"  {uuid}: read failed: {exc}")

        print("\nSubscribing to heart rate notifications for 15s...")

        def on_hr(_, data: bytearray) -> None:
            print(f"  HR notify: {data.hex()}")

        await client.start_notify(HR_MEASUREMENT_CHAR, on_hr)
        await asyncio.sleep(15)
        await client.stop_notify(HR_MEASUREMENT_CHAR)

    print("\nDone. Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
