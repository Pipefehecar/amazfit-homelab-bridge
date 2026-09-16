# Protocol notes — Amazfit GTS 2e (Huami classic BLE)

Working knowledge accumulated during development, kept here so it
survives context resets. No secrets in this file — auth key and MAC
live only in `.env` (gitignored).

## Device identity

- Model: Amazfit GTS 2e, firmware `v0.70.17.18`, algorithm `v1.7.1.1`
- BLE MAC is **fixed** (not a rotating private address) — confirmed by
  repeated scans and cross-checked against the value shown on-watch under
  Settings → About → Bluetooth MAC.
- Auth: classic Huami handshake (Mi Band 3-6 era), NOT the "chunked"
  protocol used by GTR4/newer Zepp OS devices. `amazfit_pyclient` targets
  the chunked protocol and does not apply here beyond general inspiration.

## BLE behavioral quirks (read before debugging "the watch disappeared")

1. **Advertises only for a few seconds after screen-wake.** It does not
   advertise continuously while idle. A "not found" scan burst does not
   mean "far away" — it can just mean the screen is asleep. Confirmed via
   LightBlue on iOS behaving identically to our own scans.

2. **Single connection slot.** Like most BLE peripherals with one
   connection slot, it stops advertising entirely while a central holds
   an open connection — normal, not a bug.

3. **Critical: unclean process death leaves the watch unreachable.**
   If whatever holds the BLE connection dies via SIGKILL (`kill -9`,
   `fuser -k`, a crash) instead of a clean disconnect, the watch's
   firmware never gets the disconnect handshake. It keeps thinking it's
   connected to a phantom central and won't advertise or accept new
   connections again until a long timeout elapses or it's physically
   restarted. **Always stop the demo server with Ctrl+C or `kill <pid>`
   (SIGTERM), never `kill -9` / `fuser -k`.** Reproduced and verified
   firsthand: repeated `fuser -k` restarts made the watch invisible even
   to LightBlue; a clean SIGTERM restart did not.

4. **`BleakClient(mac).connect()` does not actively scan on Linux/BlueZ.**
   It only succeeds if BlueZ already has the device cached from a prior
   discovery. Use `BleakScanner.find_device_by_address()` first (see
   `connection.py`) — otherwise every connect attempt raises
   `BleakDeviceNotFoundError` immediately even while the watch is
   advertising nearby.

## Auth handshake (classic Huami)

Characteristic: `00000009-0000-3512-2118-0009af100700` (service `fee1`).

1. Write `[0x02, 0x00]` — request random number.
2. Watch notifies `[0x10, 0x02, 0x01] + <16 random bytes>`. (Note: the
   response echoes the sent command byte at offset 1, not a fixed `0x01`
   — an earlier assumption of `[0x10, 0x01, 0x01]` was wrong and cost
   debugging time.)
3. AES-128-ECB encrypt those 16 bytes with the auth key as the AES key.
4. Write `[0x03, 0x00] + <16 encrypted bytes>`.
5. Watch notifies `[0x10, 0x03, 0x01]` (success) or `[..., 0x04]` (fail).

## GATT map (relevant characteristics, all under classic short-UUID family `xxxxxxxx-0000-3512-2118-0009af100700` unless noted)

| Characteristic | Purpose | Notes |
|---|---|---|
| `00000006` (fee0) | Battery | `raw[0]` is a packet-type marker (`0x0f`), **`raw[1]` is the actual level %**. Confirmed against watch settings (57%, 56%, 49%...). |
| `00000007` (fee0) | Realtime steps | `raw[0]` marker (`0x0c`), then 3× uint32 LE: `steps` (raw[1:5]), `distance_m` (raw[5:9]), `calories` (raw[9:13]). Confirmed against a recent step-count reset. |
| `00002a37` (standard HR measurement) | HR notify | Standard Bluetooth SIG format: flags byte, then uint8 or uint16 LE depending on flag bit 0. |
| `00002a39` (standard HR control point) | HR control | Sequence for single reading: write `[0x15,0x02,0x00]`, `[0x15,0x01,0x00]`, `[0x15,0x02,0x01]`, then wait for a `2a37` notify. Continuous: `[0x15,0x01,0x00]` then `[0x15,0x01,0x01]`. |
| `00002a46` (standard Alert Notification Service "New Alert") | Custom notifications | **Tested, does not work.** Write succeeds (BLE ack) with no visible effect on screen — twice confirmed against the real device. Huami firmware likely needs its own vendor notification format instead of generic ANS; not reverse-engineered yet. |
| `00000004`/`00000005` (fee0) | Activity fetch log | Historical sleep/stress/detailed activity data lives here behind a multi-step binary streaming protocol. Not reverse-engineered — `read_activity_log()` is a stub. |

## Presence/RSSI

- Empirically, in this user's specific setup, **RSSI ≥ -74 dBm ≈ inside
  the office**. This is a location-specific calibration, not a general
  rule — re-calibrate if the router/walls/desk position change.
- The demo's shared `near_threshold_dbm` (used by `/presence-page`'s
  slider) and the dedicated `/office-page`'s fixed `-74` threshold are
  independent — changing one does not affect the other.

## Known-experimental / not working

- `send_notification()` (ANS-based) — write succeeds, nothing shows on
  screen. Documented as broken, not silently left ambiguous.
- `read_activity_log()` — stub, `NotImplementedError`.
