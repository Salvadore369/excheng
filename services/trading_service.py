from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN

import pandas as pd

from config.settings import AppSettings
from data.historical_data import timeframe_milliseconds
from engine.state import StateMachine
from execution.bitunix_client import BitunixClient, BitunixWebSocket
from execution.base_exchange import ExchangeError
from execution.paper_exchange import PaperExchange
from models.domain import AppState, Direction, Order, OrderSide, SignalType
from risk.risk_manager import RiskError, RiskManager
from strategies.registry import create_strategy, strategy_spec


class TradingService:
    """GUI-independent engine with explicit, verified live-stop behavior."""

    def __init__(self, market, settings: AppSettings, logger: Callable[[str, str], None]) -> None:
        self.market, self.settings, self.log = market, settings, logger
        self.state = StateMachine()
        self.paper = PaperExchange(market, Decimal(str(settings.paper_initial_balance)), Decimal(str(settings.trading_fee)), Decimal(str(settings.slippage)), Decimal(str(settings.leverage)))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws_threads: list[threading.Thread] = []
        self._public_ws: BitunixWebSocket | None = None
        self._private_ws: BitunixWebSocket | None = None
        self._executor = self.paper
        self.strategy = create_strategy(settings)
        self.strategy_name = strategy_spec(settings.strategy).name
        self._last_signal_time = None
        self.last_price = Decimal(0)
        self.last_update: datetime | None = None
        self.rest_connected = False
        self.public_websocket_connected = False
        self.private_websocket_connected = False
        self.live_account: dict = {}
        self.live_positions = []
        self.live_pending_orders: list[dict] = []
        self.live_state_updated_at: datetime | None = None
        self.current_trend = "WAITING"
        self.current_signal = SignalType.NONE.value
        self._sp2l_expires_at: datetime | None = None
        self._sp2l_first_fill_at: datetime | None = None
        self._sp2l_order_ids: set[str] = set()
        self._sp2l_client_prefix: str | None = None
        self._limit_plan_time_stop_bars = settings.sp2l_time_stop_bars
        self._diagnostic_order_submitted = False

    def start_paper(self) -> None:
        self.state.start(AppState.RUNNING_PAPER)
        self._stop.clear(); self._executor = self.paper; self.private_websocket_connected = False
        self._start_websockets(private=False)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="paper-engine")
        self._thread.start()
        self.log("TRADE", "[PAPER BOT STARTED]")

    def start_live(self, exchange) -> None:
        if self.settings.position_mode != "ONE_WAY":
            raise ValueError("Initial live execution supports ONE_WAY position mode only")
        account = exchange.get_account("USDT")
        if account.get("positionMode") != "ONE_WAY":
            raise ValueError("Bitunix account is not in ONE_WAY position mode after consent and verification")
        instrument = exchange.get_instrument(self.settings.symbol)
        if not instrument.min_leverage <= self.settings.leverage <= instrument.max_leverage:
            raise ValueError(f"Leverage must be between {instrument.min_leverage} and {instrument.max_leverage}")
        if exchange.get_positions(self.settings.symbol):
            raise ValueError(f"Close the existing {self.settings.symbol} position before starting CodexBot Live")
        if exchange.get_pending_orders(self.settings.symbol):
            raise ValueError(f"Clear pending {self.settings.symbol} orders before starting CodexBot Live")
        mode = exchange.get_leverage_margin_mode(self.settings.symbol)
        if int(mode.get("leverage", -1)) != self.settings.leverage or mode.get("marginMode") != self.settings.margin_mode:
            raise ValueError("Bitunix leverage or margin mode does not match the confirmed CodexBot settings")
        self.live_account = account
        self.live_positions = []
        self.live_pending_orders = []
        self.live_state_updated_at = datetime.now(UTC)
        self.state.start(AppState.RUNNING_LIVE)
        self._stop.clear(); self._executor = exchange
        self._start_websockets(private=True)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="live-engine")
        self._thread.start()
        self.log("WARNING", "[LIVE BOT STARTED — EXISTING POSITIONS WILL REMAIN OPEN ON STOP]")

    @staticmethod
    def _kline_channel(timeframe: str) -> str:
        suffix = {"1m":"1min", "3m":"3min", "5m":"5min", "15m":"15min", "30m":"30min", "1h":"60min", "1d":"1day", "3d":"3day", "1w":"1week", "1M":"1month"}.get(timeframe, timeframe)
        return f"market_kline_{suffix}"

    def _start_websockets(self, *, private: bool) -> None:
        if not isinstance(self.market, BitunixClient):
            return
        self._public_ws = BitunixWebSocket()
        subscriptions = [{"symbol": self.settings.symbol, "ch": "ticker"}, {"symbol": self.settings.symbol, "ch": self._kline_channel(self.settings.entry_timeframe)}]
        public_thread = threading.Thread(target=lambda: asyncio.run(self._public_ws.run(subscriptions, self._public_message)), daemon=True, name="bitunix-public-ws")
        self._ws_threads.append(public_thread); public_thread.start()
        if private and self.market._api_key and self.market._api_secret:
            self._private_ws = BitunixWebSocket(self.market._api_key, self.market._api_secret)
            private_thread = threading.Thread(target=lambda: asyncio.run(self._private_ws.run([{"ch":"order"}, {"ch":"position"}], self._private_message, private=True)), daemon=True, name="bitunix-private-ws")
            self._ws_threads.append(private_thread); private_thread.start()

    async def _public_message(self, message: dict) -> None:
        if message.get("type") == "status":
            connected = message.get("status") == "connected"
            self.public_websocket_connected = connected
            if connected:
                self.log("EXCHANGE", "[BITUNIX PUBLIC WEBSOCKET CONNECTED]")
            else:
                detail = message.get("detail") or message.get("error") or "connection lost"
                self.log("EXCHANGE", f"[BITUNIX PUBLIC WEBSOCKET RECONNECTING: {detail}]")
            return
        self.public_websocket_connected = bool(self._public_ws and self._public_ws.connected)
        channel, data = str(message.get("ch", "")), message.get("data")
        if channel == "ticker" and isinstance(data, dict):
            value = data.get("la") or data.get("lastPrice") or data.get("last")
            if value is not None:
                self.last_price = Decimal(str(value)); self.last_update = datetime.now(UTC)
        elif channel.startswith("market_kline_") and isinstance(data, dict) and self._executor is self.paper:
            try:
                for event in self.paper.process_price(self.settings.symbol, Decimal(str(data["h"])), Decimal(str(data["l"]))):
                    self.log("TRADE", f"[PAPER {event} HIT]")
            except (KeyError, ValueError):
                self.log("WARNING", "Malformed Bitunix kline WebSocket update ignored")

    async def _private_message(self, message: dict) -> None:
        if message.get("type") == "status":
            connected = message.get("status") == "connected"
            self.private_websocket_connected = connected
            if connected:
                self.log("EXCHANGE", "[BITUNIX PRIVATE WEBSOCKET CONNECTED]")
            else:
                detail = message.get("detail") or message.get("error") or "connection lost"
                self.log("EXCHANGE", f"[BITUNIX PRIVATE WEBSOCKET RECONNECTING: {detail}]")
            return
        self.private_websocket_connected = bool(self._private_ws and self._private_ws.connected)
        channel = str(message.get("ch", "")).upper()
        if channel in {"ORDER", "POSITION"}:
            data = message.get("data")
            event = data.get("event", "UPDATE") if isinstance(data, dict) else "UPDATE"
            self.log("EXCHANGE", f"[BITUNIX {channel} EVENT: {event}]")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                stale = self.last_update is None or (datetime.now(UTC) - self.last_update).total_seconds() > 30
                if stale:
                    self.last_price = self.market.get_last_price(self.settings.symbol)
                    self.last_update = datetime.now(UTC)
                if self._executor is not self.paper:
                    self._refresh_live_state()
                self.rest_connected = True
            except Exception as exc:  # noqa: BLE001 - service loop must survive adapter failures
                self.rest_connected = False
                self.log("ERROR", f"Market update failed: {type(exc).__name__}: {exc}")
                self._stop.wait(15.0)
                continue
            try:
                self._evaluate()
            except Exception as exc:  # noqa: BLE001 - one bad strategy cycle must not stop protection
                self.log("ERROR", f"Strategy cycle failed: {type(exc).__name__}: {exc}")
            self._stop.wait(15.0)

    def _refresh_live_state(self) -> None:
        self.live_account = self._executor.get_account("USDT")
        self.live_positions = self._executor.get_positions(self.settings.symbol)
        self.live_pending_orders = self._executor.get_pending_orders(self.settings.symbol)
        self.live_state_updated_at = datetime.now(UTC)

    @staticmethod
    def is_codexbot_order(order: dict) -> bool:
        return str(order.get("clientId", "")).startswith("cb")

    def get_owned_pending_orders(self, *, refresh: bool = False) -> list[dict]:
        if self._executor is self.paper:
            return []
        if refresh:
            self.live_pending_orders = self._executor.get_pending_orders(self.settings.symbol)
        return [order for order in self.live_pending_orders if self.is_codexbot_order(order)]

    def get_live_positions(self, *, refresh: bool = False):
        if self._executor is self.paper:
            return []
        if refresh:
            self.live_positions = self._executor.get_positions(self.settings.symbol)
        return list(self.live_positions)

    def _cancel_live_order_ids_verified(self, order_ids, *, exchange=None, symbol=None) -> None:
        adapter = exchange or self._executor
        order_symbol = symbol or self.settings.symbol
        expected = {str(order_id) for order_id in order_ids if order_id}
        if not expected:
            return
        for order_id in expected:
            adapter.cancel_order(order_symbol, order_id)
        remaining = expected
        for _ in range(6):
            rows = adapter.get_pending_orders(order_symbol)
            if adapter is self._executor:
                self.live_pending_orders = rows
            pending_ids = {str(order.get("orderId", "")) for order in rows}
            remaining = expected & pending_ids
            if not remaining:
                return
            time.sleep(0.25)
        raise ExchangeError(f"Bitunix did not confirm cancellation of CodexBot orders: {', '.join(sorted(remaining))}")

    def cancel_owned_pending_orders(self, *, exchange=None, symbol=None) -> int:
        adapter = exchange or self._executor
        if adapter is self.paper:
            return 0
        order_symbol = symbol or self.settings.symbol
        rows = adapter.get_pending_orders(order_symbol)
        owned = [order for order in rows if self.is_codexbot_order(order)]
        self._cancel_live_order_ids_verified((order.get("orderId") for order in owned), exchange=adapter, symbol=order_symbol)
        if adapter is self._executor:
            self.live_positions = adapter.get_positions(self.settings.symbol)
        return len(owned)

    def cancel_all_owned_pending_orders(self, exchange) -> int:
        owned = [order for order in exchange.get_pending_orders() if self.is_codexbot_order(order)]
        symbols = {str(order.get("symbol") or self.settings.symbol) for order in owned}
        for symbol in symbols:
            ids = [order.get("orderId") for order in owned if str(order.get("symbol") or self.settings.symbol) == symbol]
            self._cancel_live_order_ids_verified(ids, exchange=exchange, symbol=symbol)
        return len(owned)

    def place_test_order(self, exchange, order: Order) -> dict:
        """Place one real limit order, reconcile it, and cancel unfilled quantity.

        This deliberately does not auto-close a fill. The attached exchange-side
        SL/TP remains the protection if a marketable test limit fills before the
        cancellation reaches Bitunix.
        """
        if self.state.state != AppState.STOPPED:
            raise ValueError("Stop paper/live trading and backtests before placing a test order")
        if order.order_type != "LIMIT" or order.price is None:
            raise ValueError("Test Order supports protected LIMIT orders only")
        placed = exchange.place_order(order)
        if not placed.id:
            raise ExchangeError("Bitunix did not return a test order ID")

        detail: dict = {}
        cancel_attempted = False
        try:
            # Give the matching engine a short window to expose the authoritative
            # status before deciding whether cancellation is required.
            for attempt in range(8):
                candidate = exchange.get_order(order_id=placed.id)
                if not isinstance(candidate, dict):
                    raise ExchangeError("Bitunix returned malformed test-order details")
                detail = candidate
                if str(detail.get("status", "INIT")).upper() != "INIT":
                    break
                if attempt < 7:
                    time.sleep(0.2)

            status = str(detail.get("status", "INIT")).upper()
            cancel_attempted = status not in {"FILLED", "CANCELED", "REJECTED"}
            if cancel_attempted:
                self._cancel_live_order_ids_verified([placed.id], exchange=exchange, symbol=order.symbol)
                final = exchange.get_order(order_id=placed.id)
                if isinstance(final, dict):
                    detail = final
        except Exception as original:
            # Once place_order returns, always make a best-effort cancellation on
            # reconciliation failures. If cancellation cannot be verified, tell
            # the user to manage the known order ID directly on Bitunix.
            try:
                self._cancel_live_order_ids_verified([placed.id], exchange=exchange, symbol=order.symbol)
            except Exception as cancel_error:
                raise ExchangeError(
                    f"Test order {placed.id} was accepted but automatic cancellation could not be verified; "
                    "manage it immediately on Bitunix"
                ) from cancel_error
            raise original

        final_status = str(detail.get("status", "UNKNOWN")).upper()
        traded_quantity = Decimal(str(detail.get("tradeQty") or detail.get("filledQty") or "0"))
        return {
            "order_id": placed.id,
            "client_id": placed.client_id,
            "status": final_status,
            "trade_quantity": traded_quantity,
            "cancel_attempted": cancel_attempted,
            "may_have_position": traded_quantity > 0 or final_status in {"FILLED", "PART_FILLED", "PARTIALLY_FILLED"},
            "detail": detail,
        }

    def _wait_for_no_live_positions(self) -> None:
        for _ in range(20):
            positions = self._executor.get_positions(self.settings.symbol)
            self.live_positions = positions
            if not positions:
                return
            time.sleep(0.25)
        raise ExchangeError(f"Bitunix did not confirm closure of the {self.settings.symbol} position")

    def close_live_positions(self) -> int:
        """Close every current-symbol position with reduce-only market orders."""
        if self._executor is self.paper:
            return 0
        positions = self._executor.get_positions(self.settings.symbol)
        self.live_positions = positions
        for position in positions:
            side = OrderSide.SELL if position.direction == Direction.LONG else OrderSide.BUY
            self._executor.place_order(Order(
                symbol=position.symbol,
                side=side,
                quantity=position.quantity,
                reduce_only=True,
            ))
        if positions:
            self._wait_for_no_live_positions()
        return len(positions)

    def _recent_frame(self, timeframe: str) -> pd.DataFrame:
        step = timeframe_milliseconds(timeframe); now_ms = int(datetime.now(UTC).timestamp() * 1000)
        # Ask for a window ending before the currently forming candle so an
        # EMA200 strategy can still receive 200 completed bars from a 200-row API.
        rows = self.market.get_klines(
            self.settings.symbol,
            timeframe,
            end_ms=now_ms - step,
            limit=200,
        )
        normalized = []
        for item in rows:
            timestamp = int(item["time"])
            if timestamp + step > now_ms: continue
            open_, high, low, close = map(float, (item["open"], item["high"], item["low"], item["close"]))
            normalized.append({"timestamp":pd.to_datetime(timestamp, unit="ms", utc=True), "open":open_, "high":max(high,open_,close), "low":min(low,open_,close), "close":close, "volume":float(item.get("baseVol",0))})
        if not normalized:
            return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
        return pd.DataFrame(normalized).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    def _evaluate(self) -> None:
        entry = self._recent_frame(self.settings.entry_timeframe); higher = self._recent_frame(self.settings.higher_timeframe)
        if len(entry) < self.strategy.warmup_bars or len(higher) < self.strategy.warmup_bars:
            self.current_signal = SignalType.NONE.value
            self.log("SIGNAL", "[SIGNAL REJECTED: INDICATOR WARM-UP INCOMPLETE]"); return
        prepared = self.strategy.prepare(entry, higher)
        if prepared.empty:
            self.current_signal = SignalType.NONE.value
            self.log("SIGNAL", "[SIGNAL REJECTED: STRATEGY RETURNED NO READY ROWS]")
            return
        row = prepared.iloc[-1]
        signal_time = pd.Timestamp(row["entry_close_time"]).to_pydatetime()
        self.current_trend, self.current_signal = str(row["trend"]), str(row["signal"])
        self.log("SIGNAL", f"[{row['trend']} TREND] signal={row['signal']} rsi={row['rsi']:.2f}")
        if getattr(self.strategy, "uses_limit_plans", False):
            self._maintain_sp2l_plan(signal_time)
        if getattr(self.strategy, "diagnostic_one_shot", False) and self._diagnostic_order_submitted:
            self.current_signal = SignalType.NONE.value
            return
        if row["signal"] not in {SignalType.LONG.value, SignalType.SHORT.value} or signal_time == self._last_signal_time: return
        self._last_signal_time = signal_time
        if self.settings.block_weekends and datetime.now(UTC).weekday() >= 5:
            self.log("RISK", "[SIGNAL REJECTED: WEEKEND LIQUIDITY BLACKOUT]"); return
        if self.settings.macro_event_blackout:
            self.log("RISK", "[SIGNAL REJECTED: MANUAL CPI/FOMC BLACKOUT]"); return
        if self._executor is not self.paper:
            pending = self._executor.get_pending_orders(self.settings.symbol)
            if pending:
                owner = "CODEXBOT" if any(self.is_codexbot_order(order) for order in pending) else "EXTERNAL"
                self.log("RISK", f"[SIGNAL REJECTED: {owner} PENDING ORDER EXISTS]"); return
        if len(self._executor.get_positions(self.settings.symbol)) >= self.settings.max_open_positions:
            self.log("RISK", "[SIGNAL REJECTED: MAXIMUM OPEN POSITIONS]"); return
        if getattr(self.strategy, "uses_limit_plans", False):
            self._execute_sp2l_plan(row, signal_time)
            return
        direction = Direction(str(row["signal"])); entry_price = self.last_price; instrument = self.market.get_instrument(self.settings.symbol)
        stop = RiskManager.quantize_price(RiskManager.stop_loss(entry_price, Decimal(str(row["atr"])), Decimal(str(self.settings.atr_stop_multiplier)), direction), instrument)
        target = RiskManager.quantize_price(RiskManager.take_profit(entry_price, stop, Decimal(str(self.settings.risk_reward)), direction), instrument)
        balance = self.paper.available_balance if self._executor is self.paper else Decimal(str(self._executor.get_account("USDT")["available"]))
        try:
            slippage = Decimal(str(self.settings.slippage))
            adverse_entry = entry_price * (
                Decimal(1) + slippage
                if direction == Direction.LONG
                else Decimal(1) - slippage
            )
            quantity = RiskManager.position_size(balance, Decimal(str(self.settings.risk_per_trade)), adverse_entry, stop, instrument, Decimal(str(self.settings.leverage)), Decimal(str(self.settings.trading_fee)))
        except RiskError as exc:
            self.log("RISK", f"[SIGNAL REJECTED: {exc}]"); return
        side = OrderSide.BUY if direction == Direction.LONG else OrderSide.SELL
        self.log("RISK", f"[RISK VALIDATION PASSED] qty={quantity} SL={stop} TP={target}")
        filled = self._executor.place_order(Order(self.settings.symbol, side, quantity, stop_loss=stop, take_profit=target))
        if getattr(self.strategy, "diagnostic_one_shot", False):
            self._diagnostic_order_submitted = True
        if self._executor is self.paper:
            self.log("TRADE", f"[PAPER ORDER EXECUTED] id={filled.id} {direction} {quantity}"); return
        self.log("TRADE", f"[LIVE ORDER SUBMITTED] id={filled.id} {direction} {quantity}")
        for _ in range(5):
            if self._stop.wait(0.5): break
            detail = self._executor.get_order(filled.id); status = str(detail.get("status", "UNKNOWN"))
            if status in {"FILLED", "CANCELED"}:
                self.log("TRADE", f"[LIVE ORDER {status}] id={filled.id} filled={detail.get('tradeQty','0')} fee={detail.get('fee','0')}"); break

    def _execute_sp2l_plan(self, row: pd.Series, signal_time: datetime) -> None:
        mode = "PAPER" if self._executor is self.paper else "LIVE"
        plan_name = str(getattr(self.strategy, "plan_name", "SP2L")).upper()
        client_slug = str(getattr(self.strategy, "client_slug", "sp2l")).lower()
        if self._sp2l_order_ids:
            self.log("RISK", f"[{plan_name} REJECTED: ANOTHER LIMIT PLAN IS STILL PENDING]")
            return
        if self._executor is self.paper:
            has_existing = any(order.status == "NEW" for order in self.paper.orders)
        else:
            has_existing = any(
                str(order.get("clientId", "")).startswith(f"cb{client_slug}")
                for order in self._executor.get_pending_orders(self.settings.symbol)
            )
        if has_existing:
            self.log("RISK", f"[{plan_name} REJECTED: ANOTHER CODEXBOT LIMIT PLAN EXISTS]")
            return
        levels_raw, weights_raw = row.get("entry_levels"), row.get("entry_weights")
        if not isinstance(levels_raw, (tuple, list)) or not isinstance(weights_raw, (tuple, list)):
            self.log("RISK", f"[{plan_name} REJECTED: INVALID LIMIT PLAN]")
            return
        direction = Direction(str(row["signal"]))
        instrument = self.market.get_instrument(self.settings.symbol)
        levels = [RiskManager.quantize_price(Decimal(str(level)), instrument) for level in levels_raw]
        weights = [Decimal(str(weight)) for weight in weights_raw]
        stop = RiskManager.quantize_price(Decimal(str(row["strategy_stop"])), instrument)
        tp1 = RiskManager.quantize_price(Decimal(str(row["strategy_tp1"])), instrument)
        tp2 = RiskManager.quantize_price(Decimal(str(row["strategy_tp2"])), instrument)
        weighted_entry = sum((level * weight for level, weight in zip(levels, weights, strict=True)), Decimal(0)) / sum(weights)
        try:
            balance = self.paper.available_balance if self._executor is self.paper else Decimal(str(self._executor.get_account("USDT")["available"]))
            total = RiskManager.position_size(balance, Decimal(str(self.settings.risk_per_trade)),
                weighted_entry, stop, instrument, Decimal(str(self.settings.leverage)), Decimal(str(self.settings.trading_fee)))
        except RiskError as exc:
            self.log("RISK", f"[{plan_name} REJECTED: {exc}]")
            return
        quantum = Decimal(1).scaleb(-instrument.base_precision)
        fraction = Decimal(str(row["tp1_fraction"]))
        side = OrderSide.BUY if direction == Direction.LONG else OrderSide.SELL
        submitted = []
        client_prefix = f"cb{client_slug}{int(signal_time.timestamp())}"
        sequence = 0
        try:
            for level, weight in zip(levels, weights, strict=True):
                layer = (total * weight / sum(weights)).quantize(quantum, rounding=ROUND_DOWN)
                tp1_quantity = (layer * fraction).quantize(quantum, rounding=ROUND_DOWN)
                quantities = ((tp1_quantity, tp1), (layer - tp1_quantity, tp2))
                for quantity, target in quantities:
                    if quantity < instrument.min_trade_volume:
                        continue
                    sequence += 1
                    order = self._executor.place_order(Order(self.settings.symbol, side, quantity,
                        order_type="LIMIT", price=level, stop_loss=stop, take_profit=target,
                        client_id=f"{client_prefix}{sequence:02d}"))
                    submitted.append(order)
        except Exception:
            if self._executor is self.paper:
                for order in submitted:
                    if order.id:
                        self.paper.cancel_order(self.settings.symbol, order.id)
            else:
                self._cancel_live_order_ids_verified(order.id for order in submitted)
            raise
        if not submitted:
            self.log("RISK", f"[{plan_name} REJECTED: SCALED QUANTITIES ARE BELOW THE INSTRUMENT MINIMUM]")
            return
        step = timedelta(milliseconds=timeframe_milliseconds(self.settings.entry_timeframe))
        self._sp2l_expires_at = signal_time + step * int(row["limit_expiry_bars"])
        self._sp2l_first_fill_at = None
        self._sp2l_order_ids = {str(order.id) for order in submitted if order.id}
        self._sp2l_client_prefix = client_prefix
        self._limit_plan_time_stop_bars = int(row.get("time_stop_bars", self.settings.sp2l_time_stop_bars))
        self.log("TRADE", f"[{plan_name} {mode} LIMIT PLAN ARMED] orders={len(submitted)} levels={levels} SL={stop} TP1={tp1} TP2={tp2}")

    def _maintain_sp2l_plan(self, latest_close: datetime) -> None:
        if not self._sp2l_order_ids:
            return
        mode = "PAPER" if self._executor is self.paper else "LIVE"
        plan_name = str(getattr(self.strategy, "plan_name", "SP2L")).upper()
        if self._executor is self.paper:
            pending = [order for order in self.paper.orders if order.status == "NEW" and order.id in self._sp2l_order_ids]
        else:
            pending = [
                order for order in self._executor.get_pending_orders(self.settings.symbol)
                if str(order.get("orderId")) in self._sp2l_order_ids
                or (self._sp2l_client_prefix and str(order.get("clientId", "")).startswith(self._sp2l_client_prefix))
            ]
        positions = self._executor.get_positions(self.settings.symbol)
        if pending and self._sp2l_expires_at and latest_close >= self._sp2l_expires_at:
            if self._executor is self.paper:
                for order in pending:
                    if order.id:
                        self.paper.cancel_order(self.settings.symbol, order.id)
            else:
                self._cancel_live_order_ids_verified(order.get("orderId") for order in pending)
                positions = self._executor.get_positions(self.settings.symbol)
                self.live_positions = positions
            self.log("TRADE", f"[{plan_name} {mode} LIMIT PLAN EXPIRED]")
            pending = []
        if positions and self._sp2l_first_fill_at is None:
            self._sp2l_first_fill_at = latest_close
        if positions and self._sp2l_first_fill_at is not None:
            step = timedelta(milliseconds=timeframe_milliseconds(self.settings.entry_timeframe))
            if latest_close >= self._sp2l_first_fill_at + step * self._limit_plan_time_stop_bars:
                for position in list(positions):
                    side = OrderSide.SELL if position.direction == Direction.LONG else OrderSide.BUY
                    self._executor.place_order(Order(self.settings.symbol, side, position.quantity,
                        reduce_only=True, client_id=position.id if self._executor is self.paper else None))
                for order in pending:
                    order_id = order.id if self._executor is self.paper else str(order.get("orderId", ""))
                    if order_id:
                        if self._executor is self.paper:
                            self.paper.cancel_order(self.settings.symbol, order_id)
                if self._executor is not self.paper:
                    self._cancel_live_order_ids_verified(order.get("orderId") for order in pending)
                    self._wait_for_no_live_positions()
                self.log("TRADE", f"[{plan_name} {mode} TIME STOP EXECUTED]")
                positions, pending = [], []
        if not positions and not pending:
            self._sp2l_expires_at = None
            self._sp2l_first_fill_at = None
            self._sp2l_order_ids.clear()
            self._sp2l_client_prefix = None

    def stop(self, *, cancel_owned_orders: bool = False, close_positions: bool = False) -> None:
        if self.state.state == AppState.STOPPED and self._stop.is_set():
            return
        live = self._executor is not self.paper
        # Freeze strategy execution before changing exchange state so an
        # in-flight evaluation cannot reopen a position while Stop is closing it.
        self._stop.set()
        if self._public_ws: self._public_ws.stop()
        if self._private_ws: self._private_ws.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            if self._thread.is_alive():
                raise ExchangeError("Bot engine did not stop in time; no position-close request was sent")
        if cancel_owned_orders and self._executor is not self.paper:
            cancelled = self.cancel_owned_pending_orders()
            if cancelled:
                self.log("WARNING", f"[VERIFIED {cancelled} CODEXBOT ORDERS ARE NO LONGER PENDING BEFORE STOP]")
        if live:
            if close_positions:
                closed = self.close_live_positions()
                if closed:
                    self.log("WARNING", f"[VERIFIED {closed} LIVE POSITION(S) CLOSED BEFORE STOP]")
            else:
                self.live_positions = self._executor.get_positions(self.settings.symbol)
            if self.live_positions:
                self.log("WARNING", f"[LIVE STOP LEAVES {len(self.live_positions)} OPEN POSITION(S) ON BITUNIX]")
        for thread in self._ws_threads:
            if thread.is_alive(): thread.join(timeout=3)
        self._ws_threads.clear(); self.public_websocket_connected = False; self.private_websocket_connected = False
        self.state.stop()
        position_result = "Live positions were closed and verified." if live and close_positions else "Exchange positions were left open."
        self.log("INFO", f"[BOT STOPPED] {position_result}")
