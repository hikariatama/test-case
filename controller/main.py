import asyncio
import datetime
import json
import logging
import os
from urllib.parse import quote_plus

import pytz
import websockets
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

logging.basicConfig(level=logging.WARNING)


class SensorData(BaseModel):
    datetime: datetime.datetime
    payload: int


app = FastAPI()
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
client = AsyncIOMotorClient(
    "mongodb://%s:%s@mongodb:27017/"
    % (
        quote_plus(os.getenv("MONGO_INITDB_ROOT_USERNAME")),
        quote_plus(os.getenv("MONGO_INITDB_ROOT_PASSWORD")),
    )
)
db = client["payloads"]
manipulator_db = client["manipulator"]


@app.get("/log")
async def get_manipulator_payloads_log(
    request: Request,
    start: datetime.datetime,
    end: datetime.datetime,
):
    """Request manipulator payloads log"""
    raw_records = []
    async with await client.start_session() as s:
        async for record in manipulator_db.manipulator.aggregate(
            [
                {
                    "$match": {
                        "datetime": {
                            "$gte": start,
                            "$lte": end,
                        },
                    },
                },
                {
                    "$sort": {
                        "datetime": 1,
                    },
                },
            ],
            session=s,
        ):
            raw_records.append(record)

    records = []
    current_start, current_payload = None, None
    for record in raw_records:
        if current_payload is None:
            current_start = record["datetime"]
            current_payload = record["payload"]
            continue

        if current_payload != record["payload"]:
            records.append(
                {
                    "datetime": current_start,
                    "payload": current_payload,
                }
            )
            current_start = record["datetime"]
            current_payload = record["payload"]

    if current_payload is not None:
        records.append(
            {
                "datetime": current_start,
                "payload": current_payload,
            }
        )

    for i in range(len(records)):
        records[i]["datetime"] = records[i]["datetime"].strftime("%H:%M:%S")
        records[i]["payload"] = records[i]["payload"]
        records[i]["datetime"] += " - " + (
            records[i + 1]["datetime"].strftime("%H:%M:%S")
            if i != len(records) - 1
            else datetime.datetime.now().strftime("%H:%M:%S")
        )

    return JSONResponse(
        [f"[{record['datetime']} {record['payload']}]" for record in records],
        status_code=200,
    )


@app.get("/status")
async def get_manipulator_status(request: Request):
    """Get current manipulator status"""
    async with await client.start_session() as s:
        async for record in manipulator_db.manipulator.aggregate(
            [
                {
                    "$sort": {
                        "datetime": -1,
                    },
                },
                {
                    "$limit": 1,
                },
            ],
            session=s,
        ):
            return JSONResponse(
                {
                    "status": record["payload"],
                    "datetime": record["datetime"].isoformat(),
                },
                status_code=200,
            )


@app.post("/payload")
async def submit_sensor_payload(request: Request, sensor_data: SensorData):
    """Submit payload from sensor to the database"""
    if sensor_data.payload not in range(-1000, 1000):
        return JSONResponse(
            {"error": "payload must be in range [-1000; 1000]"},
            status_code=400,
        )

    sensor_data.datetime = sensor_data.datetime.replace(tzinfo=pytz.UTC)

    if sensor_data.datetime > datetime.datetime.now(pytz.UTC):
        return JSONResponse(
            {"error": "datetime must be in the past"},
            status_code=400,
        )

    if sensor_data.datetime < datetime.datetime.now(pytz.UTC) - datetime.timedelta(minutes=5):
        return JSONResponse(
            {"error": "this payload is too old"},
            status_code=400,
        )

    async with await client.start_session() as s:
        await db.payloads.insert_one(
            {
                "datetime": sensor_data.datetime,
                "payload": sensor_data.payload,
            },
            session=s,
        )


class Sender:
    def __init__(self):
        self._last_sent = 0

    async def worker(self):
        while True:
            await self._init_websocket()

    async def _init_websocket(self):
        try:
            async with websockets.connect("ws://manipulator:8000/ws") as websocket:
                logging.debug("Connection established")
                while True:
                    await asyncio.sleep(5)
                    logging.debug("Preparing payload for manipulator")
                    payload = None
                    async with await client.start_session() as s:
                        async for record in db.payloads.aggregate(
                            [
                                {
                                    "$group": {
                                        "_id": {"$avg": "$payload"},
                                    }
                                }
                            ],
                            session=s,
                        ):
                            payload = record["_id"]
                            break

                        await db.payloads.delete_many({}, session=s)
                        payload = "up" if payload > 0 else "down"
                        await manipulator_db.manipulator.insert_one(
                            {"payload": payload, "datetime": datetime.datetime.now()},
                            session=s,
                        )

                    if payload is None:
                        logging.debug("No payload to send")
                        continue

                    logging.info("Sending payload %s to manipulator", payload)
                    await websocket.send(
                        json.dumps(
                            {
                                "datetime": datetime.datetime.now().isoformat(),
                                "status": payload,
                            }
                        )
                    )
                    logging.debug("Waiting for manipulator response")
                    response = await websocket.recv()
                    logging.debug("Received response %s", response)
        except Exception:
            logging.exception("Websocket crashed, re-initializing...")


@app.on_event("startup")
async def startup_event():
    sender = Sender()
    asyncio.ensure_future(sender.worker())
