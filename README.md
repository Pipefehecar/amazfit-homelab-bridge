# amazfit-homelab-bridge

Bridge between an Amazfit GTS 2e (Huami BLE protocol, closed firmware) and a
homelab data pipeline. This repo covers steps 2-3 of the plan: getting the
watch's BLE auth key, and exploring what it actually exposes over GATT.

## Background

The GTS 2e speaks a proprietary Huami protocol over BLE. It's already paired
to a Zepp account via the official app, so the pairing key lives on Huami's
servers — `huami-token` fetches it via the Zepp account API (no phone needed).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install huami-token
cp .env.example .env   # fill in ZEPP_EMAIL / ZEPP_PASSWORD
```

`.env` is gitignored. Never commit it.

## Step 2 — get the auth key

```bash
python scripts/get_auth_key.py
```

This runs `huami-token -m amazfit -e <email> -p <password> -b`, prints the
raw output, and tries to auto-parse the MAC + auth key into `.env`
(`AMAZFIT_MAC`, `AMAZFIT_AUTH_KEY`). If parsing fails, copy them in by hand
from the printed output.

## Step 3 — explore BLE

### 3a. Confirm the MAC is stable

```bash
python scripts/scan_mac_stability.py --rounds 5 --interval 10
```

Amazfit watches generally use a fixed public MAC (not random/rotating like
some privacy-conscious BLE peripherals), but confirm it before hardcoding
anything downstream.

### 3b. List GATT services/characteristics

```bash
python scripts/explore_gatt.py
```

Connects with `bleak`, walks every service/characteristic, prints UUIDs,
properties (read/write/notify), and reads any characteristic that allows
plain reads. Characteristics under the Huami-specific service will likely
refuse reads until the auth handshake is implemented — that's expected and
is the next milestone, not a bug in this script.

Reference for the handshake itself:
[MyrikLD/amazfit_pyclient](https://github.com/MyrikLD/amazfit_pyclient)
(built for the GTR4 over `bleak`; the GTS 2e uses the same Huami auth family
but may need firmware-version-specific tweaks).

## Project layout

```
src/amazfit_bridge/   # shared config/helpers, importable package
scripts/              # one-off runnable steps (get key, scan, explore)
.env.example          # template — copy to .env, never commit .env
```

## Roadmap (not implemented yet)

- Huami auth handshake over bleak (adapted from amazfit_pyclient)
- Data pipeline into InfluxDB + Grafana
- BLE RSSI presence detection
- Custom notifications sent to the watch
- Dashboard correlating HR/activity with GitHub commits / calendar
