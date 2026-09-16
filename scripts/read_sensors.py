"""
Authenticate against the watch and read battery, HR, and steps in that
order, logging raw payloads for each so readings can be sanity-checked
against the watch's own screen.

Usage:
    python scripts/read_sensors.py            # battery + single HR + steps
    python scripts/read_sensors.py --continuous-hr 60   # also stream HR for 60s
"""
import argparse
import asyncio
import logging

from bleak import BleakClient

from amazfit_bridge.auth import authenticate
from amazfit_bridge.config import load_watch_config
from amazfit_bridge.sensors import (
    read_battery,
    read_hr_once,
    read_steps_today,
    subscribe_hr_continuous,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("read_sensors")


async def main(continuous_hr_seconds: float | None) -> None:
    cfg = load_watch_config()
    logger.info("Connecting to %s", cfg.mac)

    async with BleakClient(cfg.mac) as client:
        logger.info("Connected. Authenticating...")
        await authenticate(client, cfg.auth_key)
        logger.info("Auth OK.\n")

        battery = await read_battery(client)
        print(f"\n=== BATTERY ===\nlevel: {battery.level_percent}%  status_byte: {battery.status_byte}  raw: {battery.raw.hex()}\n")

        bpm = await read_hr_once(client)
        print(f"=== HEART RATE (single reading) ===\n{bpm} bpm\n")

        steps = await read_steps_today(client)
        print(f"=== STEPS ===\n{steps.steps} steps  {steps.distance_m} m  {steps.calories} kcal  raw: {steps.raw.hex()}\n")

        if continuous_hr_seconds:
            print(f"=== HEART RATE (continuous, {continuous_hr_seconds}s) ===")
            readings = await subscribe_hr_continuous(client, duration=continuous_hr_seconds)
            print(f"readings: {readings}\n")

    print("Done. Disconnected.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--continuous-hr", type=float, default=None, dest="continuous_hr_seconds")
    args = parser.parse_args()

    asyncio.run(main(args.continuous_hr_seconds))
