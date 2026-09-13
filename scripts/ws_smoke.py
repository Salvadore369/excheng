"""Safe public Bitunix WebSocket connectivity smoke test (places no orders)."""
from __future__ import annotations

import asyncio

from execution.bitunix_client import BitunixWebSocket


async def check() -> bool:
    socket = BitunixWebSocket()
    messages: list[dict] = []

    async def handler(message: dict) -> None:
        messages.append(message)
        if message.get("ch") == "ticker":
            socket.stop()

    await asyncio.wait_for(socket.run([{"symbol": "BTCUSDT", "ch": "ticker"}], handler), timeout=20)
    return any(message.get("ch") == "ticker" for message in messages)


if __name__ == "__main__":
    print(f"public_ticker_received={asyncio.run(check())}")
