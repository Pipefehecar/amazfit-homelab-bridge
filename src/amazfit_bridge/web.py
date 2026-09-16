"""
Local demo web server. Not production code - just enough FastAPI to poke
the sensor functions and the new (experimental) notification/presence
features from a browser.

Run with:
    uvicorn amazfit_bridge.web:app --reload
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from amazfit_bridge import sensors
from amazfit_bridge.ble_state import BLE_LOCK, presence_age_seconds, presence_state
from amazfit_bridge.config import load_watch_config
from amazfit_bridge.connection import WatchConnection
from amazfit_bridge.presence import scan_for_rssi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("amazfit_bridge.web")

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

PRESENCE_INTERVAL_S = 6.0
PRESENCE_SCAN_BURST_S = 4.0
PRESENCE_NEAR_THRESHOLD_DBM = -70
PRESENCE_STALE_AFTER_S = 30.0


async def presence_loop(mac: str) -> None:
    while True:
        if BLE_LOCK.locked():
            presence_state.paused = True
            logger.info("Presence scan skipped - BLE lock held by a GATT operation")
        else:
            async with BLE_LOCK:
                try:
                    reading = await scan_for_rssi(
                        mac, near_threshold_dbm=PRESENCE_NEAR_THRESHOLD_DBM, timeout=PRESENCE_SCAN_BURST_S
                    )
                    presence_state.found = reading.found
                    presence_state.rssi = reading.rssi
                    presence_state.near = reading.near
                    presence_state.last_updated_ts = time.time()
                    presence_state.paused = False
                except Exception:
                    logger.exception("Presence scan burst failed")
        await asyncio.sleep(PRESENCE_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_watch_config()
    app.state.config = config
    app.state.watch = WatchConnection(config)

    task = asyncio.create_task(presence_loop(config.mac))
    yield
    task.cancel()
    await app.state.watch.close()


app = FastAPI(title="amazfit-homelab-bridge demo", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/battery")
async def get_battery():
    async with BLE_LOCK:
        client = await app.state.watch.ensure_connected()
        status = await sensors.read_battery(client)
    return {
        "level_percent": status.level_percent,
        "status_byte": status.status_byte,
        "raw_hex": status.raw.hex(),
        "confirmed": True,
    }


@app.get("/hr")
async def get_hr():
    async with BLE_LOCK:
        client = await app.state.watch.ensure_connected()
        bpm = await sensors.read_hr_once(client)
    return {"bpm": bpm, "confirmed": True}


@app.get("/activity")
async def get_activity():
    async with BLE_LOCK:
        client = await app.state.watch.ensure_connected()
        status = await sensors.read_steps_today(client)
    return {
        "steps": status.steps,
        "distance_m": status.distance_m,
        "calories": status.calories,
        "raw_hex": status.raw.hex(),
        "confirmed": True,
    }


@app.get("/presence")
async def get_presence():
    return {
        "found": presence_state.found,
        "rssi": presence_state.rssi,
        "near": presence_state.near,
        "paused": presence_state.paused,
        "age_seconds": round(presence_age_seconds(), 1),
        "stale": presence_age_seconds() > PRESENCE_STALE_AFTER_S,
        "near_threshold_dbm": PRESENCE_NEAR_THRESHOLD_DBM,
        "confirmed": False,
    }


class NotifyRequest(BaseModel):
    title: str
    body: str


@app.post("/notify")
async def post_notify(req: NotifyRequest):
    try:
        async with BLE_LOCK:
            client = await app.state.watch.ensure_connected()
            payload = await sensors.send_notification(client, req.title, req.body)
        return {"sent": True, "payload_hex": payload.hex(), "confirmed": False}
    except Exception as exc:
        logger.exception("Notification send failed")
        return JSONResponse(status_code=500, content={"sent": False, "error": str(exc), "confirmed": False})


@app.websocket("/ws/hr")
async def ws_hr(websocket: WebSocket):
    await websocket.accept()
    queue: asyncio.Queue[int] = asyncio.Queue()

    def on_reading(bpm: int) -> None:
        queue.put_nowait(bpm)

    async def collect_readings(client, hr_char, control_char, stop_event: asyncio.Event) -> None:
        def on_hr_notify(_, data: bytearray) -> None:
            on_reading(sensors._parse_hr_measurement(bytes(data)))

        await client.start_notify(hr_char, on_hr_notify)
        try:
            await client.write_gatt_char(control_char, bytes([0x15, 0x01, 0x00]))
            await client.write_gatt_char(control_char, bytes([0x15, 0x01, 0x01]))
            await stop_event.wait()
        finally:
            await client.write_gatt_char(control_char, bytes([0x15, 0x01, 0x00]))
            await client.stop_notify(hr_char)

    stop_event = asyncio.Event()
    reader_task = None

    try:
        async with BLE_LOCK:
            client = await app.state.watch.ensure_connected()
            reader_task = asyncio.create_task(
                collect_readings(client, sensors.HR_MEASUREMENT_CHAR, sensors.HR_CONTROL_POINT_CHAR, stop_event)
            )
            while True:
                bpm = await queue.get()
                await websocket.send_json({"bpm": bpm})
    except WebSocketDisconnect:
        logger.info("HR websocket client disconnected")
    finally:
        stop_event.set()
        if reader_task is not None:
            await reader_task
