"""Minimal logged IRC server and client (asyncio, RFC 1459 subset).

Server: NICK, USER, JOIN, PART, PRIVMSG, PING, QUIT. Every PRIVMSG to a channel
is appended to the hash-chained log *before* it is relayed, and it is relayed
to every member including the sender (echo-message), all inside one event-loop
step, so every client observes channel traffic in exactly log order.
"""

from __future__ import annotations

import asyncio
import re

from ledger import LogWriter

NICK_RE = re.compile(r"^[a-z][a-z0-9_-]{0,15}$")
CHAN_RE = re.compile(r"^#[a-z0-9_-]{1,32}$")
MAX_LINE = 512
SERVER = "pki.local"


class IrcServer:
    def __init__(self, log_path: str, host: str = "127.0.0.1", port: int = 0):
        self.log = LogWriter(log_path)
        self.host, self.port = host, port
        self.clients: dict[str, asyncio.StreamWriter] = {}
        self.channels: dict[str, set[str]] = {}
        self.server: asyncio.base_events.Server | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, self.host, self.port, limit=MAX_LINE * 2)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            for w in list(self.clients.values()):
                w.close()
            await self.server.wait_closed()
        self.log.close()

    def _send(self, nick: str, line: str) -> None:
        w = self.clients.get(nick)
        if w is not None and not w.is_closing():
            try:
                w.write((line + "\r\n").encode())
            except (ConnectionError, OSError):
                pass

    def _broadcast(self, chan: str, line: str) -> None:
        for member in sorted(self.channels.get(chan, ())):
            self._send(member, line)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nick: str | None = None
        registered = False

        def reply(code: str, text: str) -> None:
            writer.write(f":{SERVER} {code} {nick or '*'} {text}\r\n".encode())

        try:
            while True:
                try:
                    raw = await reader.readuntil(b"\n")
                except asyncio.LimitOverrunError:
                    reply("417", ":Input line was too long")
                    break
                except (asyncio.IncompleteReadError, ConnectionError, OSError):
                    break
                if len(raw) > MAX_LINE:
                    reply("417", ":Input line was too long")
                    continue
                try:
                    line = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    continue
                if not line:
                    continue
                cmd, _, rest = line.partition(" ")
                cmd = cmd.upper()
                if cmd == "NICK":
                    want = rest.strip().lstrip(":")
                    if not NICK_RE.match(want):
                        reply("432", f"{want} :Erroneous nickname")
                    elif want in self.clients:
                        reply("433", f"{want} :Nickname is already in use")
                    elif nick is None:
                        nick = want
                        self.clients[nick] = writer
                elif cmd == "USER" and nick and not registered:
                    registered = True
                    reply("001", f":Welcome to the ceremony network {nick}")
                elif cmd == "PING":
                    writer.write(f":{SERVER} PONG {SERVER} {rest}\r\n".encode())
                elif not registered:
                    reply("451", ":You have not registered")
                elif cmd == "JOIN":
                    chan = rest.strip()
                    if not CHAN_RE.match(chan):
                        reply("403", f"{chan} :No such channel")
                        continue
                    members = self.channels.setdefault(chan, set())
                    if nick not in members:
                        members.add(nick)
                        self.log.append("JOIN", nick, chan, "")
                        self._broadcast(chan, f":{nick}!{nick}@{SERVER} JOIN {chan}")
                    reply("353", f"= {chan} :{' '.join(sorted(members))}")
                    reply("366", f"{chan} :End of /NAMES list.")
                elif cmd == "PART":
                    chan = rest.split(" ")[0]
                    if nick in self.channels.get(chan, ()):
                        self.log.append("PART", nick, chan, "")
                        self._broadcast(chan, f":{nick}!{nick}@{SERVER} PART {chan}")
                        self.channels[chan].discard(nick)
                elif cmd == "PRIVMSG":
                    target, _, text = rest.partition(" :")
                    if target not in self.channels or nick not in self.channels[target]:
                        reply("404", f"{target} :Cannot send to channel")
                        continue
                    if any(ord(c) < 0x20 for c in text):
                        reply("417", ":Control characters are not allowed")
                        continue
                    self.log.append("PRIVMSG", nick, target, text)
                    self._broadcast(target, f":{nick}!{nick}@{SERVER} PRIVMSG {target} :{text}")
                elif cmd == "QUIT":
                    break
                else:
                    reply("421", f"{cmd} :Unknown command")
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            if nick and self.clients.get(nick) is writer:
                for chan, members in self.channels.items():
                    if nick in members:
                        members.discard(nick)
                        self.log.append("QUIT", nick, chan, "")
                        self._broadcast(chan, f":{nick}!{nick}@{SERVER} QUIT :bye")
                del self.clients[nick]
            try:
                writer.close()
            except (ConnectionError, OSError):
                pass


class IrcClient:
    """Joins one channel and yields (nick, text) for every PRIVMSG there."""

    def __init__(self, nick: str, channel: str):
        self.nick, self.channel = nick, channel
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self, host: str, port: int) -> None:
        self.reader, self.writer = await asyncio.open_connection(host, port, limit=MAX_LINE * 2)
        self._raw(f"NICK {self.nick}")
        self._raw(f"USER {self.nick} 0 * :{self.nick}")
        await self._wait_for(" 001 ")
        self._raw(f"JOIN {self.channel}")
        await self._wait_for(" 366 ")

    def _raw(self, line: str) -> None:
        data = (line + "\r\n").encode()
        if len(data) > MAX_LINE:
            raise ValueError(f"IRC line too long ({len(data)} bytes)")
        self.writer.write(data)

    async def _wait_for(self, marker: str) -> None:
        while True:
            line = (await self.reader.readline()).decode()
            if not line:
                raise ConnectionError("server closed the connection")
            if marker in line:
                return
            if " 433 " in line or " 432 " in line:
                raise ConnectionError(line.strip())

    async def say(self, text: str) -> None:
        self._raw(f"PRIVMSG {self.channel} :{text}")
        await self.writer.drain()

    async def messages(self):
        while True:
            line = await self.reader.readline()
            if not line:
                return
            line = line.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("PING"):
                self._raw("PONG" + line[4:])
                continue
            if not line.startswith(":"):
                continue
            prefix, _, rest = line[1:].partition(" ")
            cmd, _, args = rest.partition(" ")
            if cmd == "PRIVMSG":
                target, _, text = args.partition(" :")
                if target == self.channel:
                    yield prefix.split("!")[0], text

    async def close(self) -> None:
        if self.writer:
            try:
                self._raw("QUIT :done")
                await self.writer.drain()
            except (ConnectionError, RuntimeError):
                pass
            self.writer.close()
