from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable

import httpx
import websockets

from models.domain import Direction, Instrument, Order, Position, decimalize
from .base_exchange import AuthenticationError, BaseExchange, ExchangeError, TemporaryExchangeError
from risk.risk_manager import RiskManager, RiskError


REST_URL = "https://fapi.bitunix.com"
PUBLIC_WS_URL = "wss://fapi.bitunix.com/public/"
PRIVATE_WS_URL = "wss://fapi.bitunix.com/private/"


def compact_json(value: dict[str, Any] | None) -> str:
    return "" if not value else json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def canonical_query(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    return "".join(f"{key}{params[key]}" for key in sorted(params) if params[key] is not None)


def sign_request(nonce: str, timestamp: str, api_key: str, secret_key: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> str:
    digest_input = nonce + timestamp + api_key + canonical_query(params) + compact_json(body)
    digest = hashlib.sha256(digest_input.encode()).hexdigest()
    return hashlib.sha256((digest + secret_key).encode()).hexdigest()


def sign_websocket_login(nonce: str, timestamp: str, api_key: str, secret_key: str) -> str:
    """Sign Bitunix private WebSocket login without REST query canonicalization."""
    digest = hashlib.sha256((nonce + timestamp + api_key).encode()).hexdigest()
    return hashlib.sha256((digest + secret_key).encode()).hexdigest()


class BitunixClient(BaseExchange):
    """Bitunix USDT-M futures REST client, based on the official v1 futures docs."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, timeout: float = 10.0, retries: int = 3, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._retries = retries
        self._client = httpx.Client(base_url=REST_URL, timeout=timeout, transport=transport, headers={"Content-Type": "application/json", "language": "en-US"})

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, private: bool = False) -> Any:
        headers: dict[str, str] = {}
        content = compact_json(body) if body else None
        if private:
            if not self._api_key or not self._api_secret:
                raise AuthenticationError("Bitunix API credentials are not configured")
            nonce = secrets.token_hex(16)
            timestamp = str(int(time.time() * 1000))
            headers.update({
                "api-key": self._api_key, "nonce": nonce, "timestamp": timestamp,
                "sign": sign_request(nonce, timestamp, self._api_key, self._api_secret, params, body),
            })
        attempts = self._retries if method.upper() == "GET" else 1
        for attempt in range(attempts):
            try:
                response = self._client.request(method, path, params=params, content=content, headers=headers)
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt + 1 < attempts:
                        time.sleep(0.25 * (2 ** attempt))
                        continue
                    raise TemporaryExchangeError(f"Bitunix temporary HTTP error {response.status_code}")
                if response.status_code in {401, 403}:
                    raise AuthenticationError(f"Bitunix authentication failed (HTTP {response.status_code})")
                response.raise_for_status()
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ExchangeError("Bitunix returned malformed JSON") from exc
                if not isinstance(payload, dict) or "code" not in payload:
                    raise ExchangeError("Bitunix returned an unexpected response shape")
                if payload.get("code") != 0:
                    message = str(payload.get("msg") or "request rejected")[:300]
                    for secret_value in (self._api_key, self._api_secret):
                        if secret_value:
                            message = message.replace(secret_value, "[REDACTED]")
                    raise ExchangeError(f"Bitunix error {payload.get('code')}: {message}")
                return payload.get("data")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 >= attempts:
                    raise TemporaryExchangeError("Bitunix network request failed after retries") from exc
                time.sleep(0.25 * (2 ** attempt))
        raise TemporaryExchangeError("Bitunix request failed")

    def get_instrument(self, symbol: str) -> Instrument:
        data = self._request("GET", "/api/v1/futures/market/trading_pairs", params={"symbols": symbol})
        if not data:
            raise ExchangeError(f"Unknown Bitunix futures symbol: {symbol}")
        row = data[0]
        return Instrument(symbol=row["symbol"], base_precision=int(row["basePrecision"]), quote_precision=int(row["quotePrecision"]),
            min_trade_volume=decimalize(row["minTradeVolume"]), max_market_volume=decimalize(row["maxMarketOrderVolume"]),
            min_leverage=int(row["minLeverage"]), max_leverage=int(row["maxLeverage"]), status=str(row["symbolStatus"]), api_supported=bool(row["isApiSupported"]))

    def get_tickers(self, symbol: str) -> list[dict[str, Any]]:
        return self._request("GET", "/api/v1/futures/market/tickers", params={"symbols": symbol})

    def get_last_price(self, symbol: str) -> Decimal:
        data = self.get_tickers(symbol)
        if not data:
            raise ExchangeError(f"No ticker for {symbol}")
        return decimalize(data[0].get("lastPrice", data[0].get("last")))

    def get_klines(self, symbol: str, interval: str, start_ms: int | None = None, end_ms: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        params = {"symbol": symbol, "interval": interval, "limit": min(limit, 200), "type": "LAST_PRICE"}
        if start_ms is not None: params["startTime"] = start_ms
        if end_ms is not None: params["endTime"] = end_ms
        data = self._request("GET", "/api/v1/futures/market/kline", params=params)
        if not isinstance(data, list):
            raise ExchangeError("Malformed kline response")
        return data

    def get_account(self, margin_coin: str = "USDT") -> dict[str, Any]:
        data = self._request("GET", "/api/v1/futures/account", params={"marginCoin": margin_coin}, private=True)
        # The official response wraps the requested account in an array.
        if isinstance(data, list):
            if not data or not isinstance(data[0], dict):
                raise ExchangeError("Bitunix returned no account for the requested margin coin")
            return data[0]
        if isinstance(data, dict):  # Kept for backwards compatibility with older deployments.
            return data
        raise ExchangeError("Malformed Bitunix account response")

    def test_connection(self) -> dict[str, Any]:
        instrument = self.get_instrument("BTCUSDT")
        result: dict[str, Any] = {"rest": True, "authenticated": False, "instrument": instrument.symbol}
        if self._api_key and self._api_secret:
            account = self.get_account()
            result.update({
                "authenticated": True,
                "marginCoin": account.get("marginCoin", "USDT"),
                "positionMode": account.get("positionMode"),
            })
        return result

    def change_position_mode(self, position_mode: str) -> str:
        if position_mode not in {"ONE_WAY", "HEDGE"}:
            raise ValueError("position_mode must be ONE_WAY or HEDGE")
        data = self._request(
            "POST",
            "/api/v1/futures/account/change_position_mode",
            body={"positionMode": position_mode},
            private=True,
        )
        if isinstance(data, list):
            row = data[0] if data and isinstance(data[0], dict) else None
        else:
            row = data if isinstance(data, dict) else None
        if not row or row.get("positionMode") != position_mode:
            raise ExchangeError("Bitunix did not confirm the requested position mode")
        return position_mode

    def get_leverage_margin_mode(self, symbol: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            "/api/v1/futures/account/get_leverage_margin_mode",
            params={"symbol": symbol, "marginCoin": "USDT"},
            private=True,
        )
        if not isinstance(data, dict):
            raise ExchangeError("Malformed Bitunix leverage/margin-mode response")
        return data

    def place_order(self, order: Order) -> Order:
        instrument = self.get_instrument(order.symbol)
        if instrument.status != "OPEN" or not instrument.api_supported:
            raise ExchangeError(f"API trading is unavailable for {order.symbol}")
        try:
            RiskManager.validate_order(order.quantity, order.price, instrument, market=order.order_type == "MARKET")
            if order.stop_loss is not None:
                RiskManager.validate_order(order.quantity, order.stop_loss, instrument, market=False)
            if order.take_profit is not None:
                RiskManager.validate_order(order.quantity, order.take_profit, instrument, market=False)
        except RiskError as exc:
            raise ExchangeError(str(exc)) from exc
        if not order.client_id:
            order.client_id = "cb" + secrets.token_hex(12)
        body: dict[str, Any] = {"symbol": order.symbol, "qty": str(order.quantity), "side": order.side.value, "orderType": order.order_type, "reduceOnly": order.reduce_only}
        if order.price is not None: body["price"] = str(order.price)
        if order.order_type == "LIMIT": body["effect"] = "GTC"
        if order.client_id: body["clientId"] = order.client_id
        if order.stop_loss is not None: body.update({"slPrice": str(order.stop_loss), "slStopType": "LAST_PRICE", "slOrderType": "MARKET"})
        if order.take_profit is not None: body.update({"tpPrice": str(order.take_profit), "tpStopType": "LAST_PRICE", "tpOrderType": "MARKET"})
        try:
            data = self._request("POST", "/api/v1/futures/trade/place_order", body=body, private=True)
        except TemporaryExchangeError:
            # Submission outcome is ambiguous after a network failure. Never POST
            # again; reconcile by the client id sent in the original request.
            data = self.get_order(client_id=order.client_id)
        if not isinstance(data, dict) or not data.get("orderId"):
            raise ExchangeError("Malformed Bitunix place-order response")
        order.id, order.client_id, order.status = str(data["orderId"]), data.get("clientId", order.client_id), "INIT"
        return order

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        data = self._request("POST", "/api/v1/futures/trade/cancel_orders", body={"symbol": symbol, "orderList": [{"orderId": order_id}]}, private=True)
        if not isinstance(data, dict):
            raise ExchangeError("Malformed Bitunix cancel-order response")
        return any(str(item.get("orderId") or item.get("id")) == str(order_id) for item in data.get("successList", []) if isinstance(item, dict))

    def get_order(self, order_id: str | None = None, client_id: str | None = None) -> dict[str, Any]:
        if not order_id and not client_id:
            raise ValueError("order_id or client_id is required")
        params = {"orderId": order_id} if order_id else {"clientId": client_id}
        return self._request("GET", "/api/v1/futures/trade/get_order_detail", params=params, private=True)

    def get_pending_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        skip = 0
        while True:
            params: dict[str, Any] = {"limit": 100, "skip": skip}
            if symbol:
                params["symbol"] = symbol
            data = self._request("GET", "/api/v1/futures/trade/get_pending_orders", params=params, private=True)
            if not isinstance(data, dict) or not isinstance(data.get("orderList"), list):
                raise ExchangeError("Malformed Bitunix pending-orders response")
            batch = [row for row in data["orderList"] if isinstance(row, dict)]
            rows.extend(batch)
            total = int(data.get("total", len(rows)))
            if len(rows) >= total or len(batch) < 100:
                return rows
            skip += len(batch)
            if not batch or skip >= 1000:
                raise ExchangeError("Bitunix pending-order pagination exceeded the safety limit")

    def get_fills(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params = {"limit": 100}
        if symbol: params["symbol"] = symbol
        data = self._request("GET", "/api/v1/futures/trade/get_history_trades", params=params, private=True)
        return data.get("tradeList", [])

    def get_positions(self, symbol: str | None = None) -> list[Position]:
        params = {"symbol": symbol} if symbol else None
        rows = self._request("GET", "/api/v1/futures/position/get_pending_positions", params=params, private=True)
        positions = []
        for row in rows:
            # Bitunix position payloads can identify the same exposure with
            # order-side values (BUY/SELL) or position-direction values
            # (LONG/SHORT). Normalize both representations at the adapter
            # boundary so the rest of the application only sees Direction.
            raw_side = str(row.get("side", "")).upper()
            direction_by_side = {
                "BUY": Direction.LONG,
                "LONG": Direction.LONG,
                "SELL": Direction.SHORT,
                "SHORT": Direction.SHORT,
            }
            try:
                direction = direction_by_side[raw_side]
            except KeyError as exc:
                raise ExchangeError(f"Malformed Bitunix position side: {raw_side or '[missing]'}") from exc
            positions.append(Position(
                symbol=row["symbol"], direction=direction,
                quantity=decimalize(row["qty"]), entry_price=decimalize(row["avgOpenPrice"]),
                stop_loss=Decimal("0"), take_profit=Decimal("0"),
                opened_at=datetime.fromtimestamp(int(row["ctime"]) / 1000, timezone.utc),
                fees=decimalize(row.get("fee")), id=str(row["positionId"]),
            ))
        return positions

    def change_leverage(self, symbol: str, leverage: int) -> Any:
        data = self._request("POST", "/api/v1/futures/account/change_leverage", body={"marginCoin": "USDT", "symbol": symbol, "leverage": leverage}, private=True)
        row = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data
        if not isinstance(row, dict) or int(row.get("leverage", -1)) != leverage:
            raise ExchangeError("Bitunix did not confirm the requested leverage")
        return row

    def change_margin_mode(self, symbol: str, margin_mode: str) -> Any:
        data = self._request("POST", "/api/v1/futures/account/change_margin_mode", body={"marginCoin": "USDT", "symbol": symbol, "marginMode": margin_mode}, private=True)
        row = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else data
        # Older Bitunix responses used positionMode for this value despite the
        # margin-mode endpoint; accept that documented legacy response key.
        confirmed = row.get("marginMode", row.get("positionMode")) if isinstance(row, dict) else None
        if confirmed != margin_mode:
            raise ExchangeError("Bitunix did not confirm the requested margin mode")
        return row


class BitunixWebSocket:
    """Reconnectable Bitunix feed. Public subscriptions do not require credentials."""

    HEARTBEAT_INTERVAL_SECONDS = 15.0

    def __init__(self, api_key: str | None = None, api_secret: str | None = None) -> None:
        self.api_key, self.api_secret = api_key, api_secret
        self.running = False
        self.connected = False

    async def run(self, subscriptions: list[dict[str, str]], handler: Callable[[dict[str, Any]], Awaitable[None]], *, private: bool = False) -> None:
        self.running = True
        backoff = 1
        while self.running:
            try:
                async with websockets.connect(PRIVATE_WS_URL if private else PUBLIC_WS_URL, ping_interval=None, close_timeout=5) as ws:
                    self.connected, backoff = False, 1
                    last_heartbeat = time.monotonic()
                    if private:
                        if not self.api_key or not self.api_secret:
                            raise AuthenticationError("Bitunix WebSocket credentials are not configured")
                        nonce, timestamp = secrets.token_hex(16), str(int(time.time()))
                        params = {"apiKey": self.api_key, "nonce": nonce, "timestamp": int(timestamp)}
                        signature = sign_websocket_login(nonce, timestamp, self.api_key, self.api_secret)
                        await ws.send(compact_json({"op": "login", "args": [{**params, "sign": signature}]}))
                        deadline = time.monotonic() + 10
                        login: dict[str, Any] | None = None
                        while time.monotonic() < deadline:
                            response = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic())))
                            if response.get("op") == "connect":
                                continue
                            if response.get("op") == "login":
                                login = response
                                break
                        data = login.get("data") if isinstance(login, dict) else None
                        accepted = bool(isinstance(data, dict) and data.get("result") is True) or (login and login.get("code") in {0, "0"})
                        if not accepted:
                            detail = data.get("msg") if isinstance(data, dict) else None
                            message = str((login or {}).get("msg") or detail or "authentication rejected")[:200]
                            raise AuthenticationError(f"Bitunix WebSocket authentication failed: {message}")
                    self.connected = True
                    if subscriptions:
                        await ws.send(compact_json({"op": "subscribe", "args": subscriptions}))
                    await handler({"type": "status", "status": "connected", "private": private})
                    while self.running:
                        now = time.monotonic()
                        heartbeat_due_in = max(0.1, self.HEARTBEAT_INTERVAL_SECONDS - (now - last_heartbeat))
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=min(5.0, heartbeat_due_in))
                        except asyncio.TimeoutError:
                            pass
                        else:
                            message = json.loads(raw)
                            # Bitunix application-level heartbeat frames are transport
                            # housekeeping, not ticker/order updates.
                            if message.get("op") not in {"ping", "pong"}:
                                await handler(message)
                        # Check the deadline after every received frame as well as on
                        # timeout. A busy ticker must not prevent client heartbeats.
                        now = time.monotonic()
                        if now - last_heartbeat >= self.HEARTBEAT_INTERVAL_SECONDS:
                            await ws.send(compact_json({"op": "ping", "ping": int(time.time())}))
                            last_heartbeat = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.connected = False
                if not self.running: break
                await handler({"type": "status", "status": "reconnecting", "private": private, "error": type(exc).__name__, "detail": str(exc)[:200]})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        self.connected = False

    def stop(self) -> None:
        self.running = False
