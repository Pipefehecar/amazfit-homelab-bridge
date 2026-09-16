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
[MyrikLD/amazfit_pyclient](https://github.com/MyrikLD/amazfit_pyclient) —
**doesn't directly apply**: it targets the newer "chunked" protocol
(GTR4/Zepp OS). The GTS 2e speaks the older classic Huami protocol (Mi Band
3-6 era), implemented from scratch in `src/amazfit_bridge/auth.py` and
verified end-to-end against the real watch.

## Step 4 — sensor reads (validated against the real device)

`src/amazfit_bridge/sensors.py`:
- `read_battery()` — confirmed against the watch's own battery %.
- `read_hr_once()` / `subscribe_hr_continuous()` — standard BLE Heart Rate
  service, confirmed against the watch's live HR display.
- `read_steps_today()` — steps/distance/calories, confirmed against a
  recent step-count reset.
- `send_notification()` — **experimental, tested and NOT working**: writes
  to the standard Alert Notification Service (`0x2A46`/`0x1811`) succeed
  with no BLE error, but nothing appears on the watch screen. Huami
  firmware likely needs its own vendor notification format instead of
  generic ANS — not yet reverse-engineered.
- `read_activity_log()` — stub, not implemented. Stress score and sleep
  phases aren't exposed as simple characteristics; they live behind a
  multi-step binary "activity fetch" log protocol (`00000004`/`00000005`
  under `fee0`) that hasn't been reverse-engineered yet.

Try it directly:

```bash
python scripts/read_sensors.py                    # battery + HR once + steps
python scripts/read_sensors.py --continuous-hr 60  # + 60s of live HR
```

## Step 5 — local web demo

```bash
uvicorn amazfit_bridge.web:app --reload
```

Opens a single-page dashboard (`static/index.html`) at `http://127.0.0.1:8000`:

- Battery / HR (single + live via WebSocket) / activity panels — confirmed
  working, wrap `sensors.py` over one persistent authenticated connection.
- Presence panel — passive RSSI scan every ~6s, near/far by threshold.
  Experimental; the watch only advertises briefly after screen-wake, so
  "not found" doesn't reliably mean "far away."
- Notification form — experimental, marked as not working in the UI (see
  above); left in so the next attempt has a known-bad baseline.
- A shared BLE lock serializes GATT operations against presence scanning
  (one adapter can't do both at once); the UI shows a "presence paused"
  banner whenever a sensor read or live HR session is holding the lock.

## Project layout

```
src/amazfit_bridge/   # config, auth handshake, sensors, presence, web app
scripts/              # one-off runnable steps (get key, scan, explore, read)
static/               # single-page demo frontend
.env.example          # template — copy to .env, never commit .env
```

## Roadmap (not implemented yet)

- Working custom notifications (needs Huami's actual vendor format)
- Activity-fetch log protocol for sleep phases / stress score
- Data pipeline into InfluxDB + Grafana
- Dashboard correlating HR/activity with GitHub commits / calendar
