import asyncio
import json
import logging
import sys
import traceback

import websockets
from discord.ext import commands

from .events import *

log = logging.getLogger(__name__)


class WebSocket:
    def __init__(
        self, bot: commands.Bot, host: str, port: int, password: str, user_id: int, node
    ):
        self.bot = bot
        self.host = host
        self.port = port
        self.password = password
        self.user_id = user_id
        self._connection_id = None

        self.metadata = None

        self._ws = None
        self._task = None

        self.headers = {
            "Authorization": password,
            "Andesite-Resume-Id": self._connection_id,
        }

        self._node = node

    @property
    def is_connected(self):
        return self._ws is not None and self._ws.open

    async def _connect(self):
        await self.bot.wait_until_ready()

        uri = f"ws://{self.host}:{self.port}/websocket?user-id={self.user_id}"

        try:
            self._ws = await websockets.connect(uri=uri, extra_headers=self.headers)
        except Exception as er:
            return log.warning(er)

        if not self._task:
            self._task = self.bot.loop.create_task(self._listen())

        self._closed = False

        log.debug(f"[WEBSOCKET] Connected to {self.host} on port {self.port}")

    async def _listen(self):
        while True:
            try:
                data = await self._ws.recv()
            except websockets.ConnectionClosed as e:

                if e.code == 4001:
                    log.warning("[WEBSOCKET] Incorrect authentication.")
                    break

                elif e.code == 4002:
                    log.warning(
                        f"[WEBSOCKET] Closed with code 4002, attempting reconnect."
                    )
                    await self._connect()
                    break
                else:
                    log.warning(f"[WEBSOCKET] Closed with code {e.code}")
                    break

            if data:
                data = json.loads(data)

                op = data.get("op", None)
                if op == "connection-id":
                    self._connection_id = data.get("id")
                    log.debug(
                        f"[WEBSOCKET] Received connection-id of {self._connection_id}"
                    )

                elif op == "metadata":
                    self.metadata = data["data"]
                    log.debug("[WEBSOCKET] Received metadata payload.")
                elif op == "player-update":
                    try:
                        await self._node.players[int(data["guildId"])].update_state(
                            data
                        )
                    except Exception as er:
                        log.warning(f"[WEBSOCKET] Error in player-state data {data}")

                elif op == "event":
                    player = self._node.players[
                        int(data["guildId"])
                    ]  # getting the player that all events use, apart from websocket close.

                    if data["type"] == "TrackStartEvent":
                        await self._node._client.dispatch(
                            TrackStartEvent(player, data["track"])
                        )

                else:
                    log.debug(f"[WEBSOCKET] opcode {op} returned {data}")

    async def _send(self, **data):
        if self.is_connected:
            log.debug(f"[WEBSOCKET] Sending payload {data}")
            await self._ws.send(json.dumps(data))
