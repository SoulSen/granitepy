import logging
import time
import json

from discord.ext import commands

from .events import Event
from .objects import Track
from .filters import Filter

log = logging.getLogger(__name__)


class Player:
    def __init__(self, bot: commands.bot, guild_id: int, node):
        self.bot = bot
        self.guild_id = guild_id
        self.node = node

        self.last_update = None
        self.last_position = None
        self.last_state = None
        self.position_timestamp = None

        self._voice_state = {}

        self.volume = 100
        self.paused = False
        self.current = None
        self.channel_id = None

    @property
    def is_connected(self):
        return self.channel_id is not None

    async def update_state(self, state: dict):
        state = state["state"]

        self.last_state = state
        self.last_update = time.time() * 1000
        self.last_position = state.get("position", 0)
        self.position_timestamp = state.get("time", 0)

    async def _voice_server_update(self, data):
        self._voice_state.update({"event": data})
        await self._dispatch_voice_update()

    async def _voice_state_update(self, data):
        self._voice_state.update({"sessionId": data["session_id"]})

        self.channel_id = data["channel_id"]

        if not self.channel_id:
            self._voice_state.clear()
            return log.debug("[STATE] no channel_id, clearning state")

        await self._dispatch_voice_update()

    async def _dispatch_voice_update(self):
        if {"sessionId", "event"} == self._voice_state.keys():
            log.debug(f"[PLAYER] Sending voice-state")
            await self.node._websocket._send(
                op="voice-server-update",
                guildId=str(self.guild_id),
                **self._voice_state,
            )

    async def connect(self, channel_id: int):
        """
        Connects to a VoiceChannel, 
        Params:
          - channel_id integer
        """
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            raise ValueError(f"Invalid guild id {self.guild_id}")

        self.channel_id = channel_id

        await self.bot.ws.voice_state(self.guild_id, str(channel_id))
        log.info(f"[PLAYER] Connected to voice channel:  {channel_id}")

    async def disconnect(self):
        """
        Figure out why it was being big dumb
        """
        await self.bot.ws.voice_state(self.guild_id, None)

    async def set_filters(self, filter_type):
        if Filter not in filter_type.__bases__:
            raise TypeError("All filters must derive from `Filter`")

        self.node._websocket._ws.send(json.dumps({"op": "filter",
                                                  **filter_type._payload,
                                                  "guildId": str(self.guild_id)}))

    async def play(self, track):
        self.last_update = 0
        self.last_position = 0
        self.position_timestamp = 0
        self.paused = False

        self.current = track

        await self.node._websocket._send(
            op="play", guildId=str(self.guild_id), track=track.id
        )
        log.debug(f"[PLAYER] Now playing {track.title} in {self.channel_id}")

    async def pause(self, pause):
        if pause is self.paused:
            return

        self.paused = pause

        await self.node._websocket._send(
            op="pause", pause=pause, guildId=str(self.guild_id)
        )

    async def seek(self, position):
        if not 0 < position < self.current.length:
            raise ValueError("Position cannot be smaller than 0 or larger than track's length")

        await self.node._websocket._send(
            op="seek", position=position, guildId=str(self.guild_id)
        )

    async def set_volume(self, volume):
        await self.node._websocket._send(
            op="volume", volume=volume, guildId=str(self.guild_id)
        )

    async def stop(self):
        pass
