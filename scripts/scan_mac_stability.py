"""
Scan for BLE devices repeatedly and confirm the Amazfit watch's MAC address
is stable across scans (i.e. not rotating due to BLE privacy features).

Usage:
    python scripts/scan_mac_stability.py [--rounds 5] [--interval 10] [--name Amazfit]
"""
import argparse
import asyncio
import sys
import time

from bleak import BleakScanner


async def scan_once(name_filter: str) -> dict[str, str]:
    devices = await BleakScanner.discover(timeout=6.0)
    found = {}
    for d in devices:
        if d.name and name_filter.lower() in d.name.lower():
            found[d.address] = d.name
    return found


async def main(rounds: int, interval: float, name_filter: str) -> None:
    seen_macs: set[str] = set()

    for i in range(1, rounds + 1):
        print(f"\n[Round {i}/{rounds}] Scanning...")
        found = await scan_once(name_filter)

        if not found:
            print("  No matching device found this round.")
        for mac, name in found.items():
            print(f"  {mac}  ({name})")
            seen_macs.add(mac)

        if i < rounds:
            time.sleep(interval)

    print("\n--- Result ---")
    if len(seen_macs) == 1:
        print(f"Stable MAC address confirmed: {seen_macs.pop()}")
    elif len(seen_macs) == 0:
        print("Never found a matching device. Check it's advertising / in range.")
        sys.exit(1)
    else:
        print(f"WARNING: multiple MACs seen ({seen_macs}). "
              "The watch may be rotating its BLE address for privacy.")
        sys.exit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--interval", type=float, default=10.0, help="seconds between scans")
    parser.add_argument("--name", type=str, default="Amazfit", help="substring to match device name")
    args = parser.parse_args()

    asyncio.run(main(args.rounds, args.interval, args.name))
