from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from pydantic import ValidationError
from PySide6.QtCore import QDate, QThread, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.controller import ApplicationController
from config.settings import AppSettings
from models.domain import AppState, Order, OrderSide
from services.export_service import export_trades_csv
from strategies.registry import STRATEGIES, strategy_spec
from .chart_view import MarketChart
from .workers import BacktestWorker


STYLE = """
QMainWindow, QWidget {background:#07101d;color:#dce8f7;font-family:'Segoe UI';font-size:12px}
QWidget#appRoot {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #07101d,stop:1 #0a1626)}
QFrame#topBar {background:#0b1727;border:1px solid #1a2d45;border-radius:12px}
QLabel#brand {font-size:23px;font-weight:800;color:#f4f9ff;letter-spacing:2px}
QLabel#subtitle {font-size:11px;color:#7187a3}
QLabel#statusPill {background:#10263b;color:#73d7ff;border:1px solid #1c4967;border-radius:10px;padding:5px 10px;font-weight:700}
QLabel#live {background:#501b27;color:#ff98aa;border:1px solid #923044;padding:6px 11px;border-radius:10px;font-weight:800}
QFrame#creditBar {background:#091523;border:1px solid #182b40;border-radius:9px}
QLabel#creditOwner {color:#e8f5ff;font-weight:800;font-size:12px}
QLabel#creditLinks {color:#63cfff} QLabel#officialWarning {color:#8b9bb0;font-size:10px}
QTabWidget::pane {border:1px solid #1a2d45;border-radius:10px;background:#081321;top:-1px}
QTabBar::tab {padding:11px 17px;margin-right:2px;background:transparent;color:#7790ad;border-bottom:2px solid transparent;font-weight:600}
QTabBar::tab:hover {color:#c8ddf5;background:#0d1c2e} QTabBar::tab:selected {color:#66d4ff;border-bottom:2px solid #25aee8;background:#0d1c2e}
QPushButton {background:#147db3;color:white;border:1px solid #2599cc;border-radius:7px;padding:8px 15px;font-weight:700}
QPushButton:hover {background:#1798d2;border-color:#4bc3f2} QPushButton:pressed {background:#0d6594} QPushButton:disabled {background:#172638;border-color:#25384e;color:#5e748e}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QDateEdit {background:#0d1b2c;color:#e6f1ff;border:1px solid #263e59;border-radius:6px;padding:7px;selection-background-color:#167fae;min-height:17px}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QDateEdit:focus {border:1px solid #32b7eb;background:#102238}
QComboBox::drop-down {border:0;width:24px} QComboBox QAbstractItemView {background:#0d1b2c;color:#e6f1ff;border:1px solid #2d4967;selection-background-color:#165f86}
QGroupBox {background:#0b1727;border:1px solid #1b3048;border-radius:9px;margin-top:12px;padding:18px 14px 12px 14px;font-weight:700;color:#8edfff}
QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 7px;background:#0b1727}
QTableWidget,QTextEdit {background:#081522;border:1px solid #1a3048;border-radius:7px;gridline-color:#172b40;selection-background-color:#164f70}
QHeaderView::section {background:#102136;color:#91a9c3;padding:8px;border:0;border-right:1px solid #1b3048;font-weight:700}
QProgressBar {background:#0b1727;border:1px solid #263e59;border-radius:5px;text-align:center;height:9px} QProgressBar::chunk {background:#20aee5;border-radius:4px}
QScrollArea {background:transparent;border:0} QScrollArea > QWidget > QWidget {background:transparent}
QScrollBar:vertical {background:#091523;width:10px;margin:2px} QScrollBar::handle:vertical {background:#294763;border-radius:5px;min-height:36px} QScrollBar::handle:vertical:hover {background:#3c6688}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0} QCheckBox {spacing:8px}
"""

COMMON_SETTINGS_FIELDS = {
    "symbol", "higher_timeframe", "entry_timeframe", "atr_stop_multiplier",
    "risk_per_trade", "risk_reward", "max_open_positions", "trading_fee",
    "slippage", "leverage", "margin_mode", "trailing_stop", "block_weekends",
    "macro_event_blackout",
}

STRATEGY_SETTINGS_FIELDS = {
    "test_strategy": {"atr_period", "rsi_period", "test_strategy_direction"},
    "grid_strategy": {
        "ema_fast", "ema_slow", "rsi_period", "atr_period", "grid_levels",
        "grid_spacing_atr", "grid_stop_buffer_atr", "grid_tp1_fraction",
        "grid_limit_expiry_bars", "grid_time_stop_bars", "grid_min_atr_percent",
        "grid_max_atr_percent", "grid_min_trend_gap_percent", "grid_max_trend_gap_percent",
    },
    "sp2l": {
        "rsi_period", "atr_period", "sp2l_min_spike_bars", "sp2l_max_spike_bars",
        "sp2l_gap_filter", "sp2l_session_filter", "sp2l_ema_origin_filter",
        "sp2l_direction_filter", "sp2l_trend_filter", "sp2l_stop_mode",
        "sp2l_entry2_mode", "sp2l_enable_third_entry", "sp2l_tp1_rr",
        "sp2l_tp1_fraction", "sp2l_time_stop_bars", "sp2l_limit_expiry_bars",
    },
    "ema_trend_pullback": {
        "ema_fast", "ema_slow", "rsi_period", "rsi_long_min", "rsi_long_max",
        "rsi_short_min", "rsi_short_max", "atr_period",
    },
    "vibe_4h_daily_breakout": {"rsi_period", "atr_period"},
    "vibe_4h_candle_confirmation": {"rsi_period", "atr_period"},
}


def validate_test_order(symbol, direction, order_size_usdt, entry, stop_loss, take_profit, leverage, equity, instrument):
    symbol = str(symbol).strip().upper()
    direction = str(direction).upper()
    order_size_usdt, entry = Decimal(str(order_size_usdt)), Decimal(str(entry))
    stop_loss, take_profit = Decimal(str(stop_loss)), Decimal(str(take_profit))
    equity, leverage = Decimal(str(equity)), int(leverage)
    if not symbol or symbol != instrument.symbol:
        raise ValueError(f"Use the exact Bitunix futures symbol {instrument.symbol}")
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("Direction must be LONG or SHORT")
    if order_size_usdt <= 0 or entry <= 0 or stop_loss <= 0 or take_profit <= 0:
        raise ValueError("USDT order size, entry, stop loss, and take profit must all be greater than zero")
    quantity_step = Decimal("1").scaleb(-instrument.base_precision)
    quantity = (order_size_usdt / entry).quantize(quantity_step, rounding=ROUND_DOWN)
    if quantity <= 0:
        raise ValueError(f"USDT order size is too small at this entry price; Bitunix requires {instrument.base_precision}-decimal base quantity")
    if quantity < instrument.min_trade_volume:
        minimum_usdt = instrument.min_trade_volume * entry
        raise ValueError(f"USDT order size is too small; minimum at this entry is approximately {minimum_usdt} USDT")
    if not instrument.min_leverage <= leverage <= instrument.max_leverage:
        raise ValueError(f"Leverage must be between {instrument.min_leverage}x and {instrument.max_leverage}x")
    for label, value in (("Entry", entry), ("Stop loss", stop_loss), ("Take profit", take_profit)):
        if max(0, -value.normalize().as_tuple().exponent) > instrument.quote_precision:
            raise ValueError(f"{label} supports at most {instrument.quote_precision} decimals for {symbol}")
    if direction == "LONG" and not stop_loss < entry < take_profit:
        raise ValueError("For LONG, stop loss must be below entry and take profit above entry")
    if direction == "SHORT" and not take_profit < entry < stop_loss:
        raise ValueError("For SHORT, take profit must be below entry and stop loss above entry")
    reward, risk = abs(take_profit - entry), abs(entry - stop_loss)
    risk_reward = reward / risk
    if risk_reward < Decimal("2"):
        raise ValueError(f"Risk/reward must be at least 2.00; this order is {risk_reward:.2f}")
    if equity <= 0:
        raise ValueError("Bitunix account equity is unavailable; test-order risk cannot be checked")
    risk_amount = risk * quantity
    risk_percent = risk_amount / equity * Decimal("100")
    if risk_percent > Decimal("1"):
        raise ValueError(f"Estimated stop risk is {risk_percent:.3f}% of equity; maximum allowed is 1.000%")
    order = Order(
        symbol=symbol,
        side=OrderSide.BUY if direction == "LONG" else OrderSide.SELL,
        quantity=quantity,
        order_type="LIMIT",
        price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    actual_notional = quantity * entry
    return order, actual_notional, risk_amount, risk_percent, risk_reward


class LiveConfirmation(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Enable LIVE Trading"); layout = QVBoxLayout(self)
        settings = getattr(getattr(parent, "controller", None), "settings", None)
        summary = "" if settings is None else (
            f"\n\nSymbol: {settings.symbol} | Strategy: {strategy_spec(settings.strategy).name} | "
            f"Risk: {settings.risk_per_trade}% | Leverage: {settings.leverage}x | Margin: {settings.margin_mode}"
        )
        diagnostic = "" if settings is None or settings.strategy != "test_strategy" else "\n\nTESTSTRATEGY WARNING: it requests one real protected MARKET order immediately after Live starts."
        warning = QLabel("REAL FUNDS MAY BE LOST. On Live stop, CodexBot only closes existing positions if you explicitly select that option. CodexBot-owned pending orders are cancelled only after a separate Stop confirmation." + summary + diagnostic + "\n\nType yes to continue.")
        warning.setWordWrap(True); layout.addWidget(warning); self.text = QLineEdit(); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to continue."); return
        super().accept()


class PositionModeConfirmation(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Change Bitunix Position Mode"); layout = QVBoxLayout(self)
        warning = QLabel(
            "Bitunix is currently in HEDGE mode. CodexBot requires ONE-WAY mode.\n\n"
            "This change applies to ALL Bitunix futures symbols. Bitunix will reject it if any futures position "
            "or pending order exists. CodexBot will not close positions or cancel orders automatically.\n\n"
            "Type yes to change the account to ONE-WAY mode."
        )
        warning.setWordWrap(True); layout.addWidget(warning); self.text = QLineEdit(); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to change position mode."); return
        super().accept()


class PendingOrdersConfirmation(QDialog):
    def __init__(self, count: int, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Remove Stale CodexBot Orders"); layout = QVBoxLayout(self)
        warning = QLabel(f"Found {count} pending order(s) created by an earlier CodexBot session. They cannot be managed safely after restart.\n\nType yes to cancel and verify them before Live starts.")
        warning.setWordWrap(True); layout.addWidget(warning); self.text = QLineEdit(); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to cancel stale CodexBot orders."); return
        super().accept()


class AccountSettingsConfirmation(QDialog):
    def __init__(self, current: dict, target_leverage: int, target_margin: str, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Change Bitunix Symbol Settings"); layout = QVBoxLayout(self)
        warning = QLabel(
            f"CodexBot needs leverage {target_leverage}x and margin mode {target_margin}.\n"
            f"Bitunix currently reports leverage {current.get('leverage')}x and margin mode {current.get('marginMode')}.\n\n"
            "This changes the selected futures symbol. Type yes to apply and verify these settings."
        )
        warning.setWordWrap(True); layout.addWidget(warning); self.text = QLineEdit(); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to change leverage or margin mode."); return
        super().accept()


class LiveStopConfirmation(QDialog):
    def __init__(self, pending_count: int, position_count: int, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Stop LIVE Trading Safely"); layout = QVBoxLayout(self)
        warning = QLabel(
            f"CodexBot has {pending_count} pending entry order(s) and Bitunix reports {position_count} open position(s) for this symbol.\n\n"
            "CodexBot-owned pending orders will be cancelled and verified before stopping. Choose below whether the current open positions should also be closed with reduce-only market orders.\n\n"
            "Type yes to confirm your selected action."
        )
        warning.setWordWrap(True); layout.addWidget(warning)
        self.close_positions = QCheckBox(f"Yes — close all {position_count} open position(s) before stopping")
        self.close_positions.setChecked(False)
        self.close_positions.setEnabled(position_count > 0)
        layout.addWidget(self.close_positions)
        leave_open = QLabel("If unchecked, open positions remain active on Bitunix and must be monitored there.")
        leave_open.setWordWrap(True); layout.addWidget(leave_open)
        self.text = QLineEdit(); self.text.setPlaceholderText("Type yes to confirm"); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to cancel pending orders and stop."); return
        super().accept()


class TestOrderConfirmation(QDialog):
    def __init__(self, order: Order, actual_notional, leverage: int, current_leverage, risk_amount, risk_percent, risk_reward, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Place REAL Bitunix Test Order"); layout = QVBoxLayout(self)
        direction = "LONG" if order.side == OrderSide.BUY else "SHORT"
        leverage_change = "" if int(current_leverage) == leverage else f"\nLeverage will change from {current_leverage}x to {leverage}x before placement."
        warning = QLabel(
            "THIS USES REAL FUNDS; BITUNIX HAS NO DEMO ORDER ENDPOINT.\n\n"
            f"{direction} {actual_notional} USDT notional @ {order.price}\n"
            f"Bitunix base quantity after precision rounding: {order.quantity} {order.symbol}\n"
            f"SL {order.stop_loss} | TP {order.take_profit} | Leverage {leverage}x\n"
            f"Estimated stop risk: {risk_amount} USDT ({risk_percent:.3f}%) | R:R {risk_reward:.2f}"
            f"{leverage_change}\n\n"
            "CodexBot will verify acceptance and immediately cancel any unfilled remainder. A marketable limit "
            "can fill before cancellation; any resulting position is NOT silently closed and must be managed on Bitunix.\n\n"
            "Type yes to place this real test order."
        )
        warning.setWordWrap(True); layout.addWidget(warning); self.text = QLineEdit(); layout.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def accept(self) -> None:
        if self.text.text().strip().lower() != "yes": QMessageBox.warning(self, "Confirmation required", "Type yes to place the real test order."); return
        super().accept()


class MainWindow(QMainWindow):
    log_signal = Signal(str, str)

    def __init__(self) -> None:
        super().__init__(); self.setWindowTitle("CodexBot — Bitunix Futures Workstation"); self.resize(1440, 900); self.setStyleSheet(STYLE)
        self.setWindowTitle("CodexBot by ErfanTrade — Bitunix Futures Workstation")
        self.setMinimumSize(1080, 700)
        self.controller = ApplicationController(self.log_signal.emit); self.result = None; self.worker = None; self.worker_thread = None
        self.log_signal.connect(self.append_log)
        root = QWidget(); root.setObjectName("appRoot"); layout = QVBoxLayout(root); layout.setContentsMargins(18,18,18,18); layout.setSpacing(12)
        top_frame=QFrame(); top_frame.setObjectName("topBar"); top=QHBoxLayout(top_frame); top.setContentsMargins(18,11,18,11)
        identity=QVBoxLayout(); identity.setSpacing(0); title=QLabel("CODEXBOT"); title.setObjectName("brand"); identity.addWidget(title)
        subtitle=QLabel("BITUNIX FUTURES WORKSTATION  •  SAFETY-FIRST EXECUTION"); subtitle.setObjectName("subtitle"); identity.addWidget(subtitle); top.addLayout(identity); top.addStretch()
        workstation=QLabel("ERFANTRADE"); workstation.setObjectName("statusPill"); workstation.setToolTip("Created by ErfanTrade"); top.addWidget(workstation)
        self.live_badge = QLabel("●  LIVE TRADING"); self.live_badge.setObjectName("live"); self.live_badge.hide(); top.addWidget(self.live_badge); layout.addWidget(top_frame)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs)
        credit_bar=QFrame(); credit_bar.setObjectName("creditBar"); credit_layout=QVBoxLayout(credit_bar); credit_layout.setContentsMargins(13,6,13,6); credit_layout.setSpacing(2)
        credit_row=QHBoxLayout(); credit_row.setSpacing(12)
        credit_owner=QLabel("© ErfanTrade  •  All credit belongs to ErfanTrade"); credit_owner.setObjectName("creditOwner"); credit_row.addWidget(credit_owner)
        credit_links=QLabel(
            '<a style="color:#63cfff;text-decoration:none" href="http://instagram.com/erfntrade">Instagram</a>'
            '  •  <a style="color:#63cfff;text-decoration:none" href="https://www.youtube.com/@ErfnTrade">YouTube</a>'
            '  •  <a style="color:#63cfff;text-decoration:none" href="https://t.me/erftrade">Telegram</a>'
        )
        credit_links.setObjectName("creditLinks"); credit_links.setOpenExternalLinks(True); credit_links.setTextInteractionFlags(Qt.TextBrowserInteraction); credit_row.addWidget(credit_links)
        credit_row.addStretch(); credit_layout.addLayout(credit_row)
        official_warning=QLabel("OFFICIAL RELEASE NOTICE  •  Copies from other sources may be modified, unsafe, or fraudulent. Use only ErfanTrade's official channels.")
        official_warning.setObjectName("officialWarning"); official_warning.setWordWrap(True); official_warning.setToolTip("Use only releases shared through ErfanTrade's official channels."); credit_layout.addWidget(official_warning)
        layout.addWidget(credit_bar); self.setCentralWidget(root)
        self._dashboard(); self._backtest(); self._chart(); self._trading(); self._settings(); self._exchange(); self._logs(); self.refresh_dashboard()
        self.dashboard_timer = QTimer(self); self.dashboard_timer.timeout.connect(self.refresh_dashboard); self.dashboard_timer.start(1000)

    def card(self, name: str, value: str = "—"):
        frame = QFrame(); frame.setObjectName("summaryCard"); frame.setStyleSheet("QFrame#summaryCard{background:#0c1929;border:1px solid #1b3149;border-radius:9px} QFrame#summaryCard:hover{border-color:#2b5877;background:#0e1e31}")
        box = QVBoxLayout(frame); box.setContentsMargins(14,11,14,12); box.setSpacing(5); label = QLabel(name.upper()); label.setStyleSheet("color:#7189a5;font-size:10px;font-weight:700;letter-spacing:1px"); val = QLabel(value); val.setStyleSheet("font-size:18px;font-weight:700;color:#eaf4ff"); box.addWidget(label); box.addWidget(val); return frame, val

    def _dashboard(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(14,16,14,14); grid = QGridLayout(); grid.setSpacing(10); self.cards = {}
        items = ["Connection", "Mode", "Symbol", "Market Price", "Balance", "Available", "Unrealized PnL", "Realized PnL", "Strategy", "HTF Trend", "Signal", "Open Position", "Bot State"]
        for i, name in enumerate(items): frame, label = self.card(name); frame.setMinimumHeight(88); self.cards[name] = label; grid.addWidget(frame, i//4, i%4)
        for column in range(4): grid.setColumnStretch(column,1)
        layout.addLayout(grid); layout.addStretch(); self.tabs.addTab(page, "Dashboard")

    def _backtest(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QGridLayout()
        self.bt_symbol = QLineEdit(self.controller.settings.symbol); self.bt_start = QDateEdit(QDate.currentDate().addMonths(-3)); self.bt_end = QDateEdit(QDate.currentDate())
        self.bt_balance = QDoubleSpinBox(); self.bt_balance.setRange(100, 100_000_000); self.bt_balance.setValue(10_000); self.bt_balance.setPrefix("$ ")
        self.bt_strategy=QComboBox(); self._populate_strategy_combo(self.bt_strategy, self.controller.settings.strategy)
        self.bt_htf=QComboBox(); self.bt_htf.addItems(["5m","15m","30m","1h","2h","4h","6h","12h","1d"]); self.bt_htf.setCurrentText(self.controller.settings.higher_timeframe)
        self.bt_entry_tf=QComboBox(); self.bt_entry_tf.addItems(["1m","3m","5m","15m","30m","1h","2h","4h"]); self.bt_entry_tf.setCurrentText(self.controller.settings.entry_timeframe)
        self.bt_fee=QDoubleSpinBox(); self.bt_fee.setDecimals(6); self.bt_fee.setRange(0,0.02); self.bt_fee.setValue(self.controller.settings.trading_fee)
        self.bt_slippage=QDoubleSpinBox(); self.bt_slippage.setDecimals(6); self.bt_slippage.setRange(0,0.02); self.bt_slippage.setValue(self.controller.settings.slippage)
        self.bt_risk=QDoubleSpinBox(); self.bt_risk.setRange(0.01,1); self.bt_risk.setValue(self.controller.settings.risk_per_trade); self.bt_risk.setSuffix(" %")
        self.bt_rr=QDoubleSpinBox(); self.bt_rr.setRange(2,20); self.bt_rr.setValue(self.controller.settings.risk_reward)
        self.bt_atr=QDoubleSpinBox(); self.bt_atr.setRange(0.1,20); self.bt_atr.setValue(self.controller.settings.atr_stop_multiplier)
        self.bt_leverage=QSpinBox(); self.bt_leverage.setRange(1,125); self.bt_leverage.setValue(self.controller.settings.leverage); self.bt_leverage.setSuffix("x")
        self.bt_weekends=QCheckBox(); self.bt_weekends.setChecked(self.controller.settings.block_weekends)
        controls=[("Symbol",self.bt_symbol),("Strategy",self.bt_strategy),("Start",self.bt_start),("End",self.bt_end),("Initial balance",self.bt_balance),("Higher timeframe",self.bt_htf),("Entry timeframe",self.bt_entry_tf),("Trading fee",self.bt_fee),("Slippage",self.bt_slippage),("Risk / trade",self.bt_risk),("Risk / reward",self.bt_rr),("ATR multiplier",self.bt_atr),("Leverage",self.bt_leverage),("Block weekend entries",self.bt_weekends)]
        for i,(label,widget) in enumerate(controls): form.addWidget(QLabel(label),i//4*2,i%4); form.addWidget(widget,i//4*2+1,i%4)
        self.run_bt = QPushButton("RUN BACKTEST"); self.cancel_bt = QPushButton("CANCEL"); self.cancel_bt.setEnabled(False); form.addWidget(self.run_bt,8,0,1,2); form.addWidget(self.cancel_bt,8,2,1,2); layout.addLayout(form)
        self.progress = QProgressBar(); layout.addWidget(self.progress)
        self.results_scroll = QScrollArea(); self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        self.results_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        results = QWidget(); results_layout = QVBoxLayout(results); results_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.metrics = QGridLayout(); self.metric_labels = {}
        metric_names = ["Starting Balance", "Final Balance", "Total Return %", "Total Trades", "Wins", "Losses", "Win Rate %", "Profit Factor", "Maximum Drawdown %", "Average Win", "Average Loss", "Average Risk/Reward", "Sharpe Ratio"]
        for i,name in enumerate(metric_names):
            frame,label=self.card(name); frame.setMinimumHeight(76); self.metric_labels[name]=label; self.metrics.addWidget(frame,i//4,i%4)
        for column in range(4): self.metrics.setColumnStretch(column, 1)
        results_layout.addLayout(self.metrics)
        self.equity = MarketChart(); self.equity.setMinimumHeight(230); results_layout.addWidget(self.equity)
        self.trade_table = QTableWidget(0, 12); self.trade_table.setHorizontalHeaderLabels(["Entry","Exit","Symbol","Direction","Size","Entry Price","Exit Price","Stop Loss","Take Profit","Fees","PnL","Reason"])
        self.trade_table.setMinimumHeight(220); self.trade_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents); self.trade_table.setEditTriggers(QAbstractItemView.NoEditTriggers); results_layout.addWidget(self.trade_table)
        buttons = QHBoxLayout(); self.export_button = QPushButton("EXPORT TRADES CSV"); self.export_button.setEnabled(False); buttons.addStretch(); buttons.addWidget(self.export_button); results_layout.addLayout(buttons)
        self.results_scroll.setWidget(results); layout.addWidget(self.results_scroll, 1)
        self.bt_strategy.currentIndexChanged.connect(self._apply_backtest_strategy_defaults)
        self.bt_entry_tf.currentTextChanged.connect(self._sync_sp2l_backtest_timeframes)
        self.run_bt.clicked.connect(self.start_backtest); self.cancel_bt.clicked.connect(self.cancel_backtest); self.export_button.clicked.connect(self.export_csv); self.tabs.addTab(page, "Backtest")

    def _chart(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(10,10,10,10); layout.setSpacing(8)
        toolbar=QFrame(); toolbar.setObjectName("topBar"); bar=QHBoxLayout(toolbar); bar.setContentsMargins(12,7,12,7)
        self.chart_market_label=QLabel(self.controller.settings.symbol); self.chart_market_label.setStyleSheet("font-size:14px;font-weight:800;color:#e8edf3"); bar.addWidget(self.chart_market_label)
        market_type=QLabel("Perpetual · Bitunix"); market_type.setStyleSheet("color:#787b86"); bar.addWidget(market_type); bar.addSpacing(12)
        self.chart_tf=QComboBox(); self.chart_tf.addItems(["5m","15m","1h","4h"]); self.chart_tf.setCurrentText(self.controller.settings.entry_timeframe); self.chart_tf.setFixedWidth(82); bar.addWidget(self.chart_tf)
        load=QPushButton("LOAD DATA"); fit=QPushButton("FIT"); fit.setToolTip("Reset chart zoom"); bar.addWidget(load); bar.addWidget(fit); bar.addStretch()
        hint=QLabel("Wheel to zoom  •  Drag to pan  •  Hover for OHLC"); hint.setStyleSheet("color:#646b78"); bar.addWidget(hint)
        layout.addWidget(toolbar); self.market_chart=MarketChart(); self.market_chart.set_market(self.controller.settings.symbol,self.chart_tf.currentText()); layout.addWidget(self.market_chart)
        load.clicked.connect(self.load_chart); fit.clicked.connect(self.market_chart.reset_view); self.chart_tf.currentTextChanged.connect(lambda timeframe:self.market_chart.set_market(self.controller.settings.symbol,timeframe)); self.tabs.addTab(page,"Chart")

    def _trading(self):
        page=QWidget(); layout=QVBoxLayout(page); mode=QHBoxLayout(); self.mode=QComboBox(); self.mode.addItems(["PAPER","LIVE"]); self.start_bot=QPushButton("START BOT"); self.stop_bot=QPushButton("STOP BOT"); self.stop_bot.setEnabled(False)
        mode.addWidget(QLabel("Operating mode")); mode.addWidget(self.mode); mode.addWidget(self.start_bot); mode.addWidget(self.stop_bot); mode.addStretch(); layout.addLayout(mode)
        note=QLabel("Paper mode uses real Bitunix market data and local simulated execution. Paper orders never call the live order endpoint.\nLive Stop asks permission to cancel CodexBot-owned pending entries; real exchange positions are never silently closed."); note.setWordWrap(True); layout.addWidget(note)
        self.trading_status=QTextEdit(); self.trading_status.setReadOnly(True); layout.addWidget(self.trading_status); self.start_bot.clicked.connect(self.start_trading); self.stop_bot.clicked.connect(self.stop_trading); self.tabs.addTab(page,"Paper / Live")

    def _settings(self):
        page=QWidget(); page_layout=QVBoxLayout(page); page_layout.setContentsMargins(18,16,18,16); page_layout.setSpacing(12)
        heading=QLabel("Strategy configuration"); heading.setStyleSheet("font-size:20px;font-weight:750;color:#f1f7ff"); page_layout.addWidget(heading)
        helper=QLabel("Choose a strategy, then tune only its parameters. Universal risk and execution controls remain available for every strategy.")
        helper.setWordWrap(True); helper.setStyleSheet("color:#7890aa;margin-bottom:3px"); page_layout.addWidget(helper)
        selector=QFrame(); selector.setObjectName("topBar"); selector_layout=QHBoxLayout(selector); selector_layout.setContentsMargins(14,10,14,10)
        selector_layout.addWidget(QLabel("ACTIVE STRATEGY")); strategy_combo=QComboBox(); strategy_combo.setMinimumWidth(330); selector_layout.addWidget(strategy_combo,1)
        self.strategy_research=QLabel(); self.strategy_research.setWordWrap(True); self.strategy_research.setStyleSheet("color:#7890aa"); selector_layout.addWidget(self.strategy_research,2); page_layout.addWidget(selector)
        settings_scroll=QScrollArea(); self.settings_scroll=settings_scroll; settings_scroll.setWidgetResizable(True); settings_scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
        settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); settings_scroll.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        settings_scroll.verticalScrollBar().setSingleStep(32)
        settings_content=QWidget(); content_layout=QVBoxLayout(settings_content); content_layout.setContentsMargins(2,2,8,10); content_layout.setSpacing(10)
        common_group=QGroupBox("UNIVERSAL  •  MARKET, RISK & EXECUTION"); common_layout=QFormLayout(common_group)
        common_layout.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter); common_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); common_layout.setVerticalSpacing(10)
        strategy_group=QGroupBox("SELECTED STRATEGY PARAMETERS"); strategy_layout=QFormLayout(strategy_group)
        strategy_layout.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter); strategy_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); strategy_layout.setVerticalSpacing(10)
        content_layout.addWidget(strategy_group); content_layout.addWidget(common_group); content_layout.addStretch()
        settings_scroll.setWidget(settings_content); page_layout.addWidget(settings_scroll,1)
        s=self.controller.settings; self.fields={}
        specs=[("symbol",QLineEdit(s.symbol)),("strategy",strategy_combo),("higher_timeframe",QComboBox()),("entry_timeframe",QComboBox()),("ema_fast",QSpinBox()),("ema_slow",QSpinBox()),("rsi_period",QSpinBox()),("rsi_long_min",QDoubleSpinBox()),("rsi_long_max",QDoubleSpinBox()),("rsi_short_min",QDoubleSpinBox()),("rsi_short_max",QDoubleSpinBox()),("atr_period",QSpinBox()),("atr_stop_multiplier",QDoubleSpinBox()),("risk_per_trade",QDoubleSpinBox()),("risk_reward",QDoubleSpinBox()),("max_open_positions",QSpinBox()),("trading_fee",QDoubleSpinBox()),("slippage",QDoubleSpinBox()),("leverage",QSpinBox()),("margin_mode",QComboBox()),("trailing_stop",QCheckBox()),("block_weekends",QCheckBox()),("macro_event_blackout",QCheckBox()),("test_strategy_direction",QComboBox()),("grid_levels",QSpinBox()),("grid_spacing_atr",QDoubleSpinBox()),("grid_stop_buffer_atr",QDoubleSpinBox()),("grid_tp1_fraction",QDoubleSpinBox()),("grid_limit_expiry_bars",QSpinBox()),("grid_time_stop_bars",QSpinBox()),("grid_min_atr_percent",QDoubleSpinBox()),("grid_max_atr_percent",QDoubleSpinBox()),("grid_min_trend_gap_percent",QDoubleSpinBox()),("grid_max_trend_gap_percent",QDoubleSpinBox()),("sp2l_min_spike_bars",QSpinBox()),("sp2l_max_spike_bars",QSpinBox()),("sp2l_gap_filter",QCheckBox()),("sp2l_session_filter",QCheckBox()),("sp2l_ema_origin_filter",QCheckBox()),("sp2l_direction_filter",QComboBox()),("sp2l_trend_filter",QComboBox()),("sp2l_stop_mode",QComboBox()),("sp2l_entry2_mode",QComboBox()),("sp2l_enable_third_entry",QCheckBox()),("sp2l_tp1_rr",QDoubleSpinBox()),("sp2l_tp1_fraction",QDoubleSpinBox()),("sp2l_time_stop_bars",QSpinBox()),("sp2l_limit_expiry_bars",QSpinBox())]
        for name,w in specs:
            self.fields[name]=w
            if isinstance(w,QComboBox):
                if name=="strategy": self._populate_strategy_combo(w, s.strategy)
                elif "timeframe" in name: w.addItems(["1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d"])
                elif name=="margin_mode": w.addItems(["ISOLATION","CROSS"])
                elif name=="sp2l_stop_mode": w.addItems(["SPIKE_ORIGIN","FOLLOW_THROUGH","SPIKE_50"])
                elif name=="sp2l_entry2_mode": w.addItems(["ENTRY_STOP_MIDPOINT","SPIKE_50","EMA60"])
                elif name=="sp2l_direction_filter": w.addItems(["BOTH","LONG","SHORT"])
                elif name=="sp2l_trend_filter": w.addItems(["NONE","EMA60","HTF_EMA60"])
                elif name=="test_strategy_direction": w.addItems(["LONG","SHORT"])
                if name!="strategy": w.setCurrentText(str(getattr(s,name)))
            elif isinstance(w,QSpinBox):
                if name=="grid_levels": w.setRange(2,5)
                elif name in {"grid_limit_expiry_bars","grid_time_stop_bars"}: w.setRange(1,200)
                else: w.setRange(1,1000)
                w.setValue(int(getattr(s,name)))
            elif isinstance(w,QDoubleSpinBox):
                w.setDecimals(6); w.setRange(0,1000)
                if name=="grid_spacing_atr": w.setRange(0.25,3)
                elif name=="grid_stop_buffer_atr": w.setRange(0.5,5)
                elif name=="grid_tp1_fraction": w.setRange(0.1,0.9)
                elif name=="grid_min_atr_percent": w.setRange(0.05,5)
                elif name=="grid_max_atr_percent": w.setRange(0.1,20)
                elif name=="grid_min_trend_gap_percent": w.setRange(0,20)
                elif name=="grid_max_trend_gap_percent": w.setRange(0.1,30)
                w.setValue(float(getattr(s,name)))
            elif isinstance(w,QCheckBox): w.setChecked(bool(getattr(s,name)))
            if name != "strategy":
                target_layout=common_layout if name in COMMON_SETTINGS_FIELDS else strategy_layout
                target_layout.addRow(name.replace("_"," ").title(),w)
        self._strategy_group=strategy_group; self._strategy_layout=strategy_layout
        self._strategy_rows={name:widget for name,widget in self.fields.items() if name not in COMMON_SETTINGS_FIELDS and name != "strategy"}
        self.fields["strategy"].currentIndexChanged.connect(self._apply_settings_strategy_defaults)
        self.fields["entry_timeframe"].currentTextChanged.connect(self._sync_sp2l_settings_timeframes)
        self._update_strategy_fields()
        save_row=QHBoxLayout(); save_hint=QLabel("Changes are validated before they are written to config.json"); save_hint.setStyleSheet("color:#657d98"); save_row.addWidget(save_hint); save_row.addStretch()
        save=QPushButton("SAVE SETTINGS"); save.setMinimumWidth(160); save.clicked.connect(self.save_settings); save_row.addWidget(save); page_layout.addLayout(save_row); self.tabs.addTab(page,"Strategy Settings")

    @staticmethod
    def _populate_strategy_combo(combo, selected):
        for spec in STRATEGIES.values():
            combo.addItem(spec.name, spec.key)
            combo.setItemData(combo.count()-1, spec.research_status, Qt.ToolTipRole)
        index=combo.findData(selected)
        combo.setCurrentIndex(index if index>=0 else 0)

    def _apply_backtest_strategy_defaults(self, _index):
        key=self.bt_strategy.currentData()
        if not key:return
        spec=strategy_spec(key)
        self.bt_entry_tf.setCurrentText(spec.entry_timeframe); self.bt_htf.setCurrentText(spec.higher_timeframe)
        self.bt_atr.setValue(spec.atr_multiplier); self.bt_rr.setValue(spec.risk_reward)
        self.bt_risk.setValue(spec.risk_percent); self.bt_leverage.setValue(spec.leverage)
        self.bt_fee.setValue(spec.trading_fee); self.bt_slippage.setValue(spec.slippage)

    def _sync_sp2l_backtest_timeframes(self, entry_timeframe):
        if self.bt_strategy.currentData() != "sp2l":
            return
        required_higher = {"1m": "5m", "5m": "15m"}.get(entry_timeframe)
        if required_higher:
            self.bt_htf.setCurrentText(required_higher)

    def _sync_sp2l_settings_timeframes(self, entry_timeframe):
        if self.fields["strategy"].currentData() != "sp2l":
            return
        required_higher = {"1m": "5m", "5m": "15m"}.get(entry_timeframe)
        if required_higher:
            self.fields["higher_timeframe"].setCurrentText(required_higher)

    def _apply_settings_strategy_defaults(self, _index):
        key=self.fields["strategy"].currentData()
        if not key:return
        spec=strategy_spec(key)
        self.fields["entry_timeframe"].setCurrentText(spec.entry_timeframe)
        self.fields["higher_timeframe"].setCurrentText(spec.higher_timeframe)
        self.fields["atr_stop_multiplier"].setValue(spec.atr_multiplier)
        self.fields["risk_reward"].setValue(spec.risk_reward)
        self.fields["risk_per_trade"].setValue(spec.risk_percent)
        self.fields["leverage"].setValue(spec.leverage)
        self.fields["trading_fee"].setValue(spec.trading_fee)
        self.fields["slippage"].setValue(spec.slippage)
        if key == "sp2l":
            defaults = AppSettings()
            for name in (
                "sp2l_min_spike_bars", "sp2l_max_spike_bars", "sp2l_gap_filter",
                "sp2l_session_filter", "sp2l_ema_origin_filter", "sp2l_direction_filter",
                "sp2l_trend_filter", "sp2l_stop_mode", "sp2l_entry2_mode",
                "sp2l_enable_third_entry", "sp2l_tp1_rr", "sp2l_tp1_fraction",
                "sp2l_time_stop_bars", "sp2l_limit_expiry_bars",
            ):
                widget, value = self.fields[name], getattr(defaults, name)
                if isinstance(widget, QComboBox):
                    widget.setCurrentText(str(value))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))
                else:
                    widget.setValue(value)
        self._update_strategy_fields()

    def _update_strategy_fields(self):
        """Show only parameters consumed by the currently selected strategy."""
        key=self.fields["strategy"].currentData()
        visible=STRATEGY_SETTINGS_FIELDS.get(key,set())
        for name,widget in self._strategy_rows.items():
            self._strategy_layout.setRowVisible(widget,name in visible)
        spec=strategy_spec(key)
        self.strategy_research.setText(spec.research_status)
        self._strategy_group.setTitle(f"{spec.name.upper()}  •  STRATEGY PARAMETERS")

    def _exchange(self):
        page=QWidget(); layout=QVBoxLayout(page)
        connection_title=QLabel("CONNECTION STATUS"); connection_title.setStyleSheet("font-size:14px;font-weight:700;color:#7dd3fc")
        layout.addWidget(connection_title); connection_form=QFormLayout(); self.exchange_labels={k:QLabel("Not tested") for k in ["Exchange","REST","Public WebSocket","Private WebSocket","Authentication","Market Data","Last Update"]}; self.exchange_labels["Exchange"].setText("Bitunix USDT-M Perpetual Futures")
        for k,v in self.exchange_labels.items(): connection_form.addRow(k,v)
        test=QPushButton("TEST CONNECTION"); test.clicked.connect(self.test_connection); connection_form.addRow(test); layout.addLayout(connection_form)

        divider=QFrame(); divider.setFrameShape(QFrame.HLine); divider.setStyleSheet("color:#1e3a5f"); layout.addWidget(divider)
        order_title=QLabel("REAL API TEST ORDER"); order_title.setStyleSheet("font-size:14px;font-weight:700;color:#fbbf24"); layout.addWidget(order_title)
        order_note=QLabel("Places one protected real LIMIT order through the Bitunix API, verifies it, and immediately cancels any unfilled remainder. Direction and quantity are required by Bitunix."); order_note.setWordWrap(True); layout.addWidget(order_note)
        order_form=QFormLayout()
        self.test_order_symbol=QLineEdit(self.controller.settings.symbol)
        self.test_order_direction=QComboBox(); self.test_order_direction.addItems(["LONG","SHORT"])
        self.test_order_size_usdt=QDoubleSpinBox(); self.test_order_size_usdt.setDecimals(2); self.test_order_size_usdt.setRange(0.01,100_000_000); self.test_order_size_usdt.setValue(10); self.test_order_size_usdt.setSuffix(" USDT")
        self.test_order_entry=QDoubleSpinBox(); self.test_order_stop=QDoubleSpinBox(); self.test_order_target=QDoubleSpinBox()
        for price in (self.test_order_entry,self.test_order_stop,self.test_order_target): price.setDecimals(8); price.setRange(0.00000001,1_000_000_000)
        self.test_order_leverage=QSpinBox(); self.test_order_leverage.setRange(1,125); self.test_order_leverage.setValue(self.controller.settings.leverage); self.test_order_leverage.setSuffix("x")
        for label,widget in (("Symbol",self.test_order_symbol),("Direction",self.test_order_direction),("Order size",self.test_order_size_usdt),("Entry price",self.test_order_entry),("Stop loss",self.test_order_stop),("Take profit",self.test_order_target),("Leverage",self.test_order_leverage)): order_form.addRow(label,widget)
        self.test_order_button=QPushButton("TEST ORDER"); self.test_order_button.clicked.connect(self.place_test_order); order_form.addRow(self.test_order_button)
        self.test_order_result=QTextEdit(); self.test_order_result.setReadOnly(True); self.test_order_result.setMaximumHeight(95); self.test_order_result.setPlaceholderText("The verified Bitunix order ID, status, fill quantity, and cancellation result will appear here."); order_form.addRow("Result",self.test_order_result)
        layout.addLayout(order_form); layout.addStretch(); self.tabs.addTab(page,"Exchange")

    def _logs(self):
        page=QWidget(); layout=QVBoxLayout(page); self.logs=QTextEdit(); self.logs.setReadOnly(True); self.logs.document().setMaximumBlockCount(3000); layout.addWidget(self.logs); self.tabs.addTab(page,"Logs")

    def append_log(self, category, message):
        colors={"ERROR":"#fb7185","WARNING":"#fbbf24","TRADE":"#34d399","SIGNAL":"#38bdf8","RISK":"#c084fc","EXCHANGE":"#60a5fa"}; color=colors.get(category,"#cbd5e1")
        stamp=datetime.now().strftime("%H:%M:%S"); self.logs.append(f'<span style="color:#64748b">{stamp}</span> <b style="color:{color}">[{category}]</b> {message}'); self.trading_status.append(f"[{category}] {message}")

    def refresh_dashboard(self):
        s=self.controller.settings; t=self.controller.trading
        streams=[]
        if t.rest_connected:streams.append("REST")
        if t.public_websocket_connected:streams.append("PUBLIC WS")
        if t.private_websocket_connected:streams.append("PRIVATE WS")
        connection=" + ".join(streams) if streams else "IDLE"
        prices={s.symbol:t.last_price} if t.last_price else {}
        live_selected=hasattr(self,"mode") and self.mode.currentText()=="LIVE"
        if live_selected and t.live_account:
            account=t.live_account
            available=Decimal(str(account.get("available") or 0)); frozen=Decimal(str(account.get("frozen") or 0)); margin=Decimal(str(account.get("margin") or 0))
            unrealized=Decimal(str(account.get("crossUnrealizedPNL") or 0))+Decimal(str(account.get("isolationUnrealizedPNL") or 0))
            balance_text=f"${available+frozen+margin:,.2f}"; available_text=f"${available:,.2f}"; unrealized_text=f"${unrealized:,.2f}"; realized_text="—"; open_positions=len(t.live_positions)
        else:
            balance_text=f"${t.paper.balance:,.2f}"; available_text=f"${t.paper.available_balance:,.2f}"; unrealized_text=f"${t.paper.unrealized_pnl(prices):,.2f}"; realized_text=f"${t.paper.realized_pnl:,.2f}"; open_positions=len(t.paper.get_positions())
        self.cards["Connection"].setText(connection); self.cards["Mode"].setText(self.mode.currentText() if hasattr(self,"mode") else "PAPER"); self.cards["Symbol"].setText(s.symbol); self.cards["Market Price"].setText(str(t.last_price or "—")); self.cards["Balance"].setText(balance_text); self.cards["Available"].setText(available_text); self.cards["Unrealized PnL"].setText(unrealized_text); self.cards["Realized PnL"].setText(realized_text); self.cards["Strategy"].setText(t.strategy_name); self.cards["HTF Trend"].setText(t.current_trend); self.cards["Signal"].setText(t.current_signal); self.cards["Open Position"].setText(str(open_positions)); self.cards["Bot State"].setText(t.state.state.value)
        if hasattr(self,"exchange_labels"):
            self.exchange_labels["REST"].setText("Connected" if t.rest_connected else "Disconnected")
            self.exchange_labels["Public WebSocket"].setText("Connected" if t.public_websocket_connected else "Disconnected")
            self.exchange_labels["Private WebSocket"].setText("Connected" if t.private_websocket_connected else "Disconnected")
            if t.last_update: self.exchange_labels["Last Update"].setText(t.last_update.astimezone().strftime("%Y-%m-%d %H:%M:%S"))

    def start_backtest(self):
        if self.controller.trading.state.state != AppState.STOPPED: QMessageBox.warning(self,"Busy","Stop trading before running a backtest."); return
        try:
            symbol=self.bt_symbol.text().strip().upper(); settings=self.controller.settings.model_copy(update={"symbol":symbol,"strategy":self.bt_strategy.currentData(),"higher_timeframe":self.bt_htf.currentText(),"entry_timeframe":self.bt_entry_tf.currentText(),"trading_fee":self.bt_fee.value(),"slippage":self.bt_slippage.value(),"risk_per_trade":self.bt_risk.value(),"risk_reward":self.bt_rr.value(),"atr_stop_multiplier":self.bt_atr.value(),"leverage":self.bt_leverage.value(),"block_weekends":self.bt_weekends.isChecked()}); self.controller.update_settings(settings)
            start=datetime.combine(self.bt_start.date().toPython(),datetime.min.time(),tzinfo=timezone.utc); end=datetime.combine(self.bt_end.date().toPython(),datetime.min.time(),tzinfo=timezone.utc)
            if start>=end: raise ValueError("Start date must be before end date")
            self.controller.trading.state.start(AppState.RUNNING_BACKTEST)
        except Exception as exc: QMessageBox.warning(self,"Invalid backtest",str(exc)); return
        self.worker_thread=QThread(self); self.worker=BacktestWorker(self.controller.backtests,start,end,Decimal(str(self.bt_balance.value()))); self.worker.moveToThread(self.worker_thread); self.worker_thread.started.connect(self.worker.run); self.worker.progress.connect(self.progress.setValue); self.worker.finished.connect(self.backtest_finished); self.worker.failed.connect(self.backtest_failed); self.worker.cancelled.connect(self.backtest_cancelled); self.worker.finished.connect(self.worker_thread.quit); self.worker.failed.connect(self.worker_thread.quit); self.worker.cancelled.connect(self.worker_thread.quit); self.run_bt.setEnabled(False); self.cancel_bt.setEnabled(True); self.worker_thread.start(); self.append_log("INFO",f"[BACKTEST STARTED] strategy={strategy_spec(settings.strategy).name} symbol={settings.symbol} entry={settings.entry_timeframe} htf={settings.higher_timeframe} risk={settings.risk_per_trade}% leverage={settings.leverage}x fee={settings.trading_fee} slippage={settings.slippage} ATR={settings.atr_stop_multiplier} R:R={settings.risk_reward} block_weekends={settings.block_weekends}")

    def cancel_backtest(self):
        if self.worker: self.worker.cancel_event.set(); self.append_log("WARNING","Backtest cancellation requested")

    def backtest_finished(self,result):
        self.controller.trading.state.stop(); self.result=result; self.run_bt.setEnabled(True); self.cancel_bt.setEnabled(False); self.export_button.setEnabled(True); self.progress.setValue(100); self.equity.set_equity(result.equity_curve)
        for name,value in result.metrics.items():
            if name in self.metric_labels: self.metric_labels[name].setText(f"{value:.3f}" if value != float("inf") else "∞")
        self.trade_table.setRowCount(len(result.trades))
        for row,trade in enumerate(result.trades):
            values=[trade.entry_time.isoformat(),trade.exit_time.isoformat(),trade.symbol,trade.direction.value,trade.size,trade.entry_price,trade.exit_price,trade.stop_loss,trade.take_profit,trade.fees,trade.pnl,trade.exit_reason]
            for col,value in enumerate(values): self.trade_table.setItem(row,col,QTableWidgetItem(str(value)))
        self.append_log("INFO",f"[BACKTEST COMPLETE] {len(result.trades)} trades, final balance {result.final_balance:.2f}"); self.refresh_dashboard()

    def backtest_failed(self,error):
        self.controller.trading.state.error(); self.controller.trading.state.stop(); self.run_bt.setEnabled(True); self.cancel_bt.setEnabled(False); self.append_log("ERROR",error); QMessageBox.critical(self,"Backtest failed",error.splitlines()[-1])

    def backtest_cancelled(self):
        self.controller.trading.state.stop(); self.run_bt.setEnabled(True); self.cancel_bt.setEnabled(False); self.append_log("WARNING","[BACKTEST CANCELLED]")

    def export_csv(self):
        if not self.result:return
        path,_=QFileDialog.getSaveFileName(self,"Export trades","exports/trades.csv","CSV Files (*.csv)")
        if not path:return
        export_trades_csv(path,self.result.trades)
        self.append_log("INFO",f"Trades exported to {path}")

    def load_chart(self):
        try:
            end=datetime.now(timezone.utc); start=end-timedelta(days=7); frame=self.controller.backtests.data.load(self.controller.settings.symbol,self.chart_tf.currentText(),start,end)
            from indicators.indicators import enrich_indicators
            frame=enrich_indicators(frame,self.controller.settings.ema_fast,self.controller.settings.ema_slow,self.controller.settings.rsi_period,self.controller.settings.atr_period)
            trades=self.result.trades if self.result and self.result.trades and self.result.trades[0].symbol==self.controller.settings.symbol else None
            self.chart_market_label.setText(self.controller.settings.symbol); self.market_chart.set_market(self.controller.settings.symbol,self.chart_tf.currentText())
            self.market_chart.set_candles(frame,trades); self.append_log("INFO",f"Loaded {len(frame)} closed candles")
        except Exception as exc: QMessageBox.warning(self,"Chart load failed",str(exc)); self.append_log("ERROR",f"Chart load failed: {exc}")

    def save_settings(self):
        try:
            data=self.controller.settings.model_dump()
            for name,w in self.fields.items():
                data[name]=w.text() if isinstance(w,QLineEdit) else w.currentData() if name=="strategy" else w.currentText() if isinstance(w,QComboBox) else w.isChecked() if isinstance(w,QCheckBox) else w.value()
            settings=AppSettings.model_validate(data); self.controller.update_settings(settings); self.bt_symbol.setText(settings.symbol); self.append_log("INFO","Settings saved (credentials are never persisted)"); self.refresh_dashboard()
        except ValidationError as exc: QMessageBox.warning(self,"Invalid settings",exc.errors()[0]["msg"])

    def test_connection(self):
        try:
            result=self.controller.client.test_connection(); now=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"); self.exchange_labels["REST"].setText("Connected"); self.exchange_labels["Public WebSocket"].setText("Connected" if self.controller.trading.public_websocket_connected else "Not started / reconnecting"); self.exchange_labels["Private WebSocket"].setText("Connected" if self.controller.trading.private_websocket_connected else "Not started / reconnecting"); self.exchange_labels["Authentication"].setText("Authenticated" if result["authenticated"] else "Credentials not configured"); self.exchange_labels["Market Data"].setText("Available"); self.exchange_labels["Last Update"].setText(now); self.append_log("EXCHANGE","[BITUNIX CONNECTION TEST PASSED]")
        except Exception as exc: self.exchange_labels["REST"].setText("Failed"); self.append_log("ERROR",f"Connection test failed: {exc}"); QMessageBox.warning(self,"Connection failed",str(exc))

    @staticmethod
    def _account_equity(account):
        explicit = account.get("accountEquity") or account.get("equity")
        if explicit not in {None, ""}:
            return Decimal(str(explicit))
        return sum((Decimal(str(account.get(key) or 0)) for key in ("available", "frozen", "margin", "crossUnrealizedPNL", "isolationUnrealizedPNL")), Decimal("0"))

    def place_test_order(self):
        if self.controller.trading.state.state != AppState.STOPPED:
            QMessageBox.warning(self,"Busy","Stop paper/live trading and backtests before placing a test order."); return
        self.test_order_button.setEnabled(False); self.test_order_result.setPlainText("Validating account and order...")
        try:
            client=self.controller.client; connection=client.test_connection()
            if not connection.get("authenticated"):
                raise ValueError("Test Order requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables")
            symbol=self.test_order_symbol.text().strip().upper(); instrument=client.get_instrument(symbol); account=client.get_account("USDT")
            order,actual_notional,risk_amount,risk_percent,risk_reward=validate_test_order(
                symbol,self.test_order_direction.currentText(),self.test_order_size_usdt.value(),self.test_order_entry.value(),
                self.test_order_stop.value(),self.test_order_target.value(),self.test_order_leverage.value(),self._account_equity(account),instrument,
            )
            account_wide=account.get("positionMode")!="ONE_WAY"
            if not self._clear_live_start_conflicts(account_wide=account_wide,symbol=symbol):return
            if not self._ensure_one_way_mode(account.get("positionMode")):return
            current=client.get_leverage_margin_mode(symbol); target_leverage=self.test_order_leverage.value()
            if TestOrderConfirmation(order,actual_notional,target_leverage,current.get("leverage",target_leverage),risk_amount,risk_percent,risk_reward,self).exec()!=QDialog.Accepted:return
            if int(current.get("leverage",-1))!=target_leverage:
                client.change_leverage(symbol,target_leverage)
                verified=client.get_leverage_margin_mode(symbol)
                if int(verified.get("leverage",-1))!=target_leverage:raise ValueError("Bitunix did not apply the confirmed test-order leverage")
                self.append_log("WARNING",f"[BITUNIX {symbol} TEST LEVERAGE CHANGED AND VERIFIED: {target_leverage}x]")
            self.test_order_result.setPlainText("Submitting real test order to Bitunix..."); QApplication.processEvents()
            result=self.controller.trading.place_test_order(client,order)
            outcome=(f"Order ID: {result['order_id']}\nSubmitted: {actual_notional} USDT ({order.quantity} base quantity)\nStatus: {result['status']} | Filled: {result['trade_quantity']}\n"
                     f"Unfilled cancellation attempted: {'yes' if result['cancel_attempted'] else 'not needed'}")
            self.test_order_result.setPlainText(outcome); self.append_log("EXCHANGE",f"[BITUNIX TEST ORDER VERIFIED] id={result['order_id']} status={result['status']} filled={result['trade_quantity']}")
            if result["may_have_position"]:
                QMessageBox.warning(self,"Test order filled",outcome+"\n\nThis test may have created a real position. Manage it immediately on Bitunix; CodexBot did not silently close it.")
            else:
                QMessageBox.information(self,"Test order verified",outcome+"\n\nBitunix accepted the API order and no fill was reported.")
        except Exception as exc:
            self.test_order_result.setPlainText(f"FAILED: {exc}"); self.append_log("ERROR",f"Test order failed: {exc}"); QMessageBox.warning(self,"Test order failed",str(exc))
        finally:
            self.test_order_button.setEnabled(True)

    def start_trading(self):
        try:
            if self.mode.currentText()=="LIVE":
                if LiveConfirmation(self).exec()!=QDialog.Accepted:return
                # Authentication is safely checked before entering live state; no order is placed.
                result=self.controller.client.test_connection()
                if not result["authenticated"]: raise ValueError("Live trading requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables")
                if not self._clear_live_start_conflicts(account_wide=result.get("positionMode")!="ONE_WAY"):return
                if not self._ensure_one_way_mode(result.get("positionMode")):return
                if not self._ensure_live_symbol_settings():return
                self.controller.trading.start_live(self.controller.client); self.live_badge.show()
            else: self.controller.trading.start_paper()
            self.start_bot.setEnabled(False); self.stop_bot.setEnabled(True); self.mode.setEnabled(False); self.refresh_dashboard()
        except Exception as exc: QMessageBox.warning(self,"Unable to start",str(exc)); self.append_log("ERROR",f"Start rejected: {exc}")

    def _ensure_one_way_mode(self, reported_mode):
        if reported_mode == "ONE_WAY":return True
        if PositionModeConfirmation(self).exec()!=QDialog.Accepted:return False
        self.controller.client.change_position_mode("ONE_WAY")
        account=self.controller.client.get_account("USDT")
        if account.get("positionMode") != "ONE_WAY": raise ValueError("Bitunix did not switch the account to ONE-WAY position mode")
        self.append_log("WARNING","[BITUNIX POSITION MODE CHANGED TO ONE-WAY WITH USER CONSENT]")
        return True

    def _clear_live_start_conflicts(self, *, account_wide=False, symbol=None):
        client=self.controller.client; symbol=symbol or self.controller.settings.symbol
        positions=client.get_positions(None if account_wide else symbol)
        if positions:
            scope="across the futures account" if account_wide else f"for {symbol}"
            raise ValueError(f"Close the existing position(s) {scope} before starting CodexBot Live")
        pending=client.get_pending_orders(None if account_wide else symbol); owned=[order for order in pending if self.controller.trading.is_codexbot_order(order)]; foreign=[order for order in pending if not self.controller.trading.is_codexbot_order(order)]
        if foreign:
            scope="across the futures account" if account_wide else f"for {symbol}"
            raise ValueError(f"Cancel the {len(foreign)} non-CodexBot pending order(s) {scope} before starting Live")
        if owned:
            if PendingOrdersConfirmation(len(owned),self).exec()!=QDialog.Accepted:return False
            cancelled=self.controller.trading.cancel_all_owned_pending_orders(client) if account_wide else self.controller.trading.cancel_owned_pending_orders(exchange=client,symbol=symbol)
            self.append_log("WARNING",f"[CANCELLED AND VERIFIED {cancelled} STALE CODEXBOT ORDERS]")
        return True

    def _ensure_live_symbol_settings(self):
        client=self.controller.client; settings=self.controller.settings
        current=client.get_leverage_margin_mode(settings.symbol)
        leverage_matches=int(current.get("leverage",-1))==settings.leverage; margin_matches=current.get("marginMode")==settings.margin_mode
        if leverage_matches and margin_matches:return True
        if AccountSettingsConfirmation(current,settings.leverage,settings.margin_mode,self).exec()!=QDialog.Accepted:return False
        if not leverage_matches:client.change_leverage(settings.symbol,settings.leverage)
        if not margin_matches:client.change_margin_mode(settings.symbol,settings.margin_mode)
        verified=client.get_leverage_margin_mode(settings.symbol)
        if int(verified.get("leverage",-1))!=settings.leverage or verified.get("marginMode")!=settings.margin_mode:raise ValueError("Bitunix did not apply the confirmed leverage and margin mode")
        self.append_log("WARNING",f"[BITUNIX {settings.symbol} SETTINGS VERIFIED: {settings.leverage}x {settings.margin_mode}]")
        return True

    def stop_trading(self):
        if not self._stop_trading_with_consent():return
        self.start_bot.setEnabled(True); self.stop_bot.setEnabled(False); self.mode.setEnabled(True); self.live_badge.hide(); self.refresh_dashboard()

    def _stop_trading_with_consent(self):
        try:
            trading=self.controller.trading; cancel_owned=False; close_positions=False
            if trading.state.state==AppState.RUNNING_LIVE:
                owned=trading.get_owned_pending_orders(refresh=True)
                positions=trading.get_live_positions(refresh=True)
                if owned or positions:
                    confirmation=LiveStopConfirmation(len(owned),len(positions),self)
                    if confirmation.exec()!=QDialog.Accepted:return False
                    close_positions=confirmation.close_positions.isChecked()
                cancel_owned=bool(owned)
            trading.stop(cancel_owned_orders=cancel_owned,close_positions=close_positions)
            return True
        except Exception as exc:
            QMessageBox.warning(self,"Unable to stop safely",str(exc)); self.append_log("ERROR",f"Stop rejected: {exc}"); return False

    def closeEvent(self,event):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker.cancel_event.set()
            if not self.worker_thread.wait(5000):
                QMessageBox.warning(self,"Backtest still stopping","Please wait for the current data request to finish, then close again.")
                event.ignore(); return
        if self.controller.trading.state.state in {AppState.RUNNING_PAPER,AppState.RUNNING_LIVE} and not self._stop_trading_with_consent():
            event.ignore(); return
        self.controller.close(); event.accept()
