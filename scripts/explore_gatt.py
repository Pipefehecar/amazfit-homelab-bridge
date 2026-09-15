"""
Connect to the Amazfit watch by MAC (from .env) and list every GATT
service / characteristic it exposes, with properties (read/write/notify)
and, for small readable non-Huami-protected values, the raw bytes.

This does NOT perform the Huami auth handshake yet — some characteristics
(e.g. under the Huami/Mi Fitness service, typically UUID prefix 0000fee1
or similar 128-bit Huami UUIDs) will refuse reads/writes until that
handshake is done. That's expected: the goal here is just to map what's
available before building the auth layer (see MyrikLD/amazfit_pyclient
for the GTR4 reference implementation of that handshake).

Usage:
    python scripts/explore_gatt.py
"""
import asyncio

from bleak import BleakClient

from amazfit_bridge.config import load_watch_config


async def main() -> None:
    cfg = load_watch_config()
    print(f"Connecting to {cfg.mac} ...")

    async with BleakClient(cfg.mac) as client:
        print(f"Connected: {client.is_connected}\n")

        for service in client.services:
            print(f"[Service] {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    [Char] {char.uuid}  props=({props})  handle={char.handle}")

                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                        print(f"        value: {value.hex()}")
                    except Exception as exc:
                        print(f"        read failed: {exc}")

                for descriptor in char.descriptors:
                    print(f"        [Descriptor] {descriptor.uuid}")

    print("\nDone. Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
