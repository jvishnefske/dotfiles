"""Small file helpers for async code: the blocking I/O runs in a worker
thread (asyncio.to_thread) so it never stalls the event loop that is serving
IRC, the RPC and the control pipes."""

from __future__ import annotations

import asyncio
import hashlib


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _write(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


async def read_bytes(path: str) -> bytes:
    return await asyncio.to_thread(_read, path)


async def write_bytes(path: str, data: bytes) -> None:
    await asyncio.to_thread(_write, path, data)


async def sha256_hex(path: str) -> str:
    return hashlib.sha256(await read_bytes(path)).hexdigest()
