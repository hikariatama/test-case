import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO)

app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = json.loads(await websocket.receive_text())
            logging.info(data)
            await websocket.send_text(json.dumps({"ok": True}))
        except WebSocketDisconnect:
            break
