"""
Obtain the BLE auth key + MAC address for the paired Amazfit watch,
using the `huami-token` PyPI package against your Zepp account,
then write both into .env (creating it from .env.example if missing).

Usage:
    python scripts/get_auth_key.py

Reads ZEPP_EMAIL / ZEPP_PASSWORD from .env (or prompts if absent).
Never pass credentials on the CLI in shell history; this script reads
them from the environment / a prompt instead.
"""
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"

MAC_RE = re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b")
KEY_RE = re.compile(r"(?:0x)?([0-9A-Fa-f]{32})\b")


def ensure_env_file() -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text())
        print(f"Created {ENV_PATH} from .env.example")


def get_credentials() -> tuple[str, str]:
    load_dotenv(ENV_PATH)
    email = os.environ.get("ZEPP_EMAIL") or input("Zepp account email: ").strip()
    password = os.environ.get("ZEPP_PASSWORD") or getpass.getpass("Zepp account password: ")
    return email, password


def run_huami_token(email: str, password: str) -> str:
    cmd = ["huami-token", "-m", "amazfit", "-e", email, "-p", password, "-b"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"huami-token exited with code {result.returncode}")
    return result.stdout


def update_env(mac: str, auth_key: str) -> None:
    lines = ENV_PATH.read_text().splitlines()
    seen = {"AMAZFIT_MAC": False, "AMAZFIT_AUTH_KEY": False}

    for i, line in enumerate(lines):
        if line.startswith("AMAZFIT_MAC="):
            lines[i] = f"AMAZFIT_MAC={mac}"
            seen["AMAZFIT_MAC"] = True
        elif line.startswith("AMAZFIT_AUTH_KEY="):
            lines[i] = f"AMAZFIT_AUTH_KEY={auth_key}"
            seen["AMAZFIT_AUTH_KEY"] = True

    if not seen["AMAZFIT_MAC"]:
        lines.append(f"AMAZFIT_MAC={mac}")
    if not seen["AMAZFIT_AUTH_KEY"]:
        lines.append(f"AMAZFIT_AUTH_KEY={auth_key}")

    ENV_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nWrote AMAZFIT_MAC and AMAZFIT_AUTH_KEY to {ENV_PATH}")


def main() -> None:
    ensure_env_file()
    email, password = get_credentials()
    output = run_huami_token(email, password)

    mac_match = MAC_RE.search(output)
    key_match = KEY_RE.search(output)

    if not mac_match or not key_match:
        sys.exit(
            "Could not auto-parse MAC/auth key from huami-token output above. "
            "Copy them manually into .env (AMAZFIT_MAC / AMAZFIT_AUTH_KEY)."
        )

    update_env(mac=mac_match.group(1), auth_key=key_match.group(1))


if __name__ == "__main__":
    main()
