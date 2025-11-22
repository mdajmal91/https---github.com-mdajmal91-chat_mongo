# main.py
import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "chatdb")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mongo client (motor)
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DB_NAME]
messages_coll = db["messages"]

# Simple in-memory connection manager per room
class ConnectionManager:
    def __init__(self):
        # room -> set of websockets
        self.active: Dict[str, Set[WebSocket]] = {}

    async def connect(self, room: str, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(room, set()).add(websocket)

    def disconnect(self, room: str, websocket: WebSocket):
        if room in self.active and websocket in self.active[room]:
            self.active[room].remove(websocket)
            if not self.active[room]:
                del self.active[room]

    async def broadcast(self, room: str, message: dict):
        if room not in self.active:
            return
        data = json.dumps(message)
        coros = [ws.send_text(data) for ws in list(self.active[room])]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

manager = ConnectionManager()

# Pydantic model for messages (used for saving to DB)
class ChatMessage(BaseModel):
    room: str
    username: str
    text: str
    ts: datetime

# Basic index page
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# HTTP endpoint to fetch last N messages for a room
@app.get("/history/{room}")
async def get_history(room: str, limit: int = Query(50, ge=1, le=1000)):
    cursor = messages_coll.find({"room": room}).sort("ts", -1).limit(limit)
    docs = []
    async for doc in cursor:
        docs.append({
            "username": doc.get("username"),
            "text": doc.get("text"),
            "ts": doc.get("ts").isoformat()
        })
    # reverse to chronological order
    docs.reverse()
    return JSONResponse(docs)

# WebSocket endpoint
# connect with: ws://host:8000/ws/{room}?username=NAME
@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str, username: str = Query(...)):
    await manager.connect(room, websocket)
    join_msg = {
        "type": "system",
        "text": f"{username} joined the chat",
        "username": "system",
        "ts": datetime.utcnow().isoformat()
    }
    # broadcast join
    await manager.broadcast(room, join_msg)

    try:
        while True:
            data = await websocket.receive_text()
            # expecting plain text message. Could be JSON in advanced usage.
            msg = ChatMessage(room=room, username=username, text=data, ts=datetime.utcnow())
            # save to mongo
            await messages_coll.insert_one(msg.dict())
            # prepare broadcast object
            out = {
                "type": "message",
                "username": username,
                "text": data,
                "ts": msg.ts.isoformat()
            }
            await manager.broadcast(room, out)
    except WebSocketDisconnect:
        manager.disconnect(room, websocket)
        leave_msg = {
            "type": "system",
            "text": f"{username} left the chat",
            "username": "system",
            "ts": datetime.utcnow().isoformat()
        }
        await manager.broadcast(room, leave_msg)
    except Exception as e:
        # handle unexpected errors: inform others
        manager.disconnect(room, websocket)
        err_msg = {
            "type": "system",
            "text": f"connection error: {str(e)}",
            "username": "system",
            "ts": datetime.utcnow().isoformat()
        }
        await manager.broadcast(room, err_msg)
