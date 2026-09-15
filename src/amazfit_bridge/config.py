import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class WatchConfig:
    mac: str
    auth_key: str


def load_watch_config() -> WatchConfig:
    mac = os.environ.get("AMAZFIT_MAC")
    auth_key = os.environ.get("AMAZFIT_AUTH_KEY")

    if not mac or not auth_key:
        raise RuntimeError(
            "AMAZFIT_MAC / AMAZFIT_AUTH_KEY not set. "
            "Copy .env.example to .env and run scripts/get_auth_key.py first."
        )

    return WatchConfig(mac=mac.upper(), auth_key=auth_key.lower())
