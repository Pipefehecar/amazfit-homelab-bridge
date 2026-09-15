"""
Classic Huami BLE auth handshake (used by Mi Band 3-6, Amazfit Bip/GTS/GTR
older generations, GTS 2e). Not to be confused with the newer "chunked"
protocol used by GTR4/Zepp OS devices (see MyrikLD/amazfit_pyclient).

Handshake, over the auth characteristic (fee1 service):
    1. Write "request random number" command.
    2. Watch notifies back a 16-byte random number.
    3. Encrypt that number with AES-128-ECB using the auth key as the key.
    4. Write the encrypted 16 bytes back.
    5. Watch notifies success/fail.
"""
import asyncio

from bleak import BleakClient
from Crypto.Cipher import AES

AUTH_CHAR_UUID = "00000009-0000-3512-2118-0009af100700"

_CMD_REQUEST_RANDOM = bytes([0x02, 0x00])
_CMD_SEND_ENCRYPTED_PREFIX = bytes([0x03, 0x00])

_RESP_RANDOM = bytes([0x10, 0x02, 0x01])
_RESP_SUCCESS = bytes([0x10, 0x03, 0x01])
_RESP_FAIL = bytes([0x10, 0x03, 0x04])

_TIMEOUT = 10


class HuamiAuthError(Exception):
    pass


async def authenticate(client: BleakClient, auth_key_hex: str) -> None:
    key = bytes.fromhex(auth_key_hex)
    if len(key) != 16:
        raise ValueError(f"auth key must be 16 bytes (32 hex chars), got {len(key)}")

    step_done = asyncio.Event()
    result: dict = {}

    def on_notify(_, data: bytearray) -> None:
        data = bytes(data)
        if data.startswith(_RESP_RANDOM):
            result["random"] = data[3:19]
            step_done.set()
        elif data.startswith(_RESP_SUCCESS):
            result["success"] = True
            step_done.set()
        elif data.startswith(_RESP_FAIL):
            result["success"] = False
            step_done.set()
        else:
            result["unexpected"] = data
            step_done.set()

    await client.start_notify(AUTH_CHAR_UUID, on_notify)
    try:
        step_done.clear()
        await client.write_gatt_char(AUTH_CHAR_UUID, _CMD_REQUEST_RANDOM, response=False)
        await asyncio.wait_for(step_done.wait(), timeout=_TIMEOUT)

        if "random" not in result:
            raise HuamiAuthError(f"unexpected response requesting random number: {result}")

        cipher = AES.new(key, AES.MODE_ECB)
        encrypted = cipher.encrypt(result["random"])

        step_done.clear()
        await client.write_gatt_char(
            AUTH_CHAR_UUID, _CMD_SEND_ENCRYPTED_PREFIX + encrypted, response=False
        )
        await asyncio.wait_for(step_done.wait(), timeout=_TIMEOUT)

        if not result.get("success"):
            raise HuamiAuthError(f"watch rejected encrypted auth key: {result}")
    finally:
        await client.stop_notify(AUTH_CHAR_UUID)
