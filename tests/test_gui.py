from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QWidget

import gui.main_window as main_window_module
from gui.main_window import LiveConfirmation, MainWindow, PositionModeConfirmation, TestOrderConfirmation as RealTestOrderConfirmation, validate_test_order
from models.domain import AppState, Instrument, OrderSide
from decimal import Decimal


def test_summary_card_style_does_not_apply_to_child_labels():
    app = QApplication.instance() or QApplication([])
    window = MainWindow.__new__(MainWindow)
    frame, value_label = window.card("Final Balance", "$ 12,345.67")
    frame.resize(260, 76)
    frame.show()
    app.processEvents()

    labels = frame.findChildren(QLabel)
    assert [label.text() for label in labels] == ["FINAL BALANCE", "$ 12,345.67"]
    assert all(label.isVisible() for label in labels)
    assert all(label.height() >= label.sizeHint().height() for label in labels)
    assert value_label.text() == "$ 12,345.67"

    frame.close()


def test_strategy_settings_only_show_selected_strategy_fields():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    settings_index = next(index for index in range(window.tabs.count()) if window.tabs.tabText(index) == "Strategy Settings")
    window.tabs.setCurrentIndex(settings_index)
    window.show()
    app.processEvents()

    strategy = window.fields["strategy"]
    strategy.setCurrentIndex(strategy.findData("grid_strategy"))
    app.processEvents()
    assert window._strategy_layout.isRowVisible(window.fields["grid_levels"])
    assert not window._strategy_layout.isRowVisible(window.fields["sp2l_min_spike_bars"])
    assert not window._strategy_layout.isRowVisible(window.fields["test_strategy_direction"])

    strategy.setCurrentIndex(strategy.findData("sp2l"))
    app.processEvents()
    assert window._strategy_layout.isRowVisible(window.fields["sp2l_min_spike_bars"])
    assert not window._strategy_layout.isRowVisible(window.fields["grid_levels"])
    assert window.fields["symbol"].isVisible()
    assert window.settings_scroll.verticalScrollBar().singleStep() == 32
    window.close()


def test_creator_credit_and_official_links_are_persistent():
    _app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert "ErfanTrade" in window.windowTitle()
    assert window.findChild(QLabel, "statusPill").text() == "ERFANTRADE"
    owner = window.findChild(QLabel, "creditOwner")
    links = window.findChild(QLabel, "creditLinks")
    warning = window.findChild(QLabel, "officialWarning")
    assert "All credit belongs to ErfanTrade" in owner.text()
    assert "http://instagram.com/erfntrade" in links.text()
    assert "https://www.youtube.com/@ErfnTrade" in links.text()
    assert "https://t.me/erftrade" in links.text()
    assert links.openExternalLinks()
    assert "modified, unsafe, or fraudulent" in warning.text()
    window.close()


def test_live_confirmation_accepts_yes_case_insensitively():
    _app = QApplication.instance() or QApplication([])
    dialog = LiveConfirmation()
    dialog.text.setText("  YES  ")

    dialog.accept()

    assert dialog.result() == QDialog.Accepted
    dialog.close()


def test_live_confirmation_warns_test_strategy_places_immediately():
    _app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.controller = SimpleNamespace(settings=SimpleNamespace(
        strategy="test_strategy", symbol="BTCUSDT", risk_per_trade=0.1,
        leverage=1, margin_mode="ISOLATION",
    ))
    dialog = LiveConfirmation(parent)
    warning = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert "immediately" in warning
    assert "MARKET order" in warning
    dialog.close(); parent.close()


def test_position_mode_change_requires_explicit_yes():
    _app = QApplication.instance() or QApplication([])
    dialog = PositionModeConfirmation()
    dialog.text.setText(" yes ")

    dialog.accept()

    assert dialog.result() == QDialog.Accepted
    dialog.close()


def test_test_order_confirmation_requires_yes():
    _app = QApplication.instance() or QApplication([])
    instrument = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)
    order, notional, risk, risk_percent, rr = validate_test_order("BTCUSDT", "LONG", "10", "100", "90", "120", 2, "1000", instrument)
    dialog = RealTestOrderConfirmation(order, notional, 2, 2, risk, risk_percent, rr)
    dialog.text.setText(" YES ")
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    dialog.close()


def test_test_order_validation_enforces_direction_rr_and_account_risk():
    instrument = Instrument("BTCUSDT", 3, 1, Decimal("0.001"), Decimal("1000"), 1, 125)
    order, notional, _, risk_percent, rr = validate_test_order("btcusdt", "SHORT", "10", "100", "110", "80", 2, "1000", instrument)
    assert order.side == OrderSide.SELL
    assert order.quantity == Decimal("0.100")
    assert notional == Decimal("10.000")
    assert risk_percent == Decimal("0.100")
    assert rr == Decimal("2")

    try:
        validate_test_order("BTCUSDT", "LONG", "100", "100", "90", "105", 2, "100", instrument)
    except ValueError as exc:
        assert "Risk/reward" in str(exc)
    else:
        raise AssertionError("sub-2R test order must be rejected")


def test_test_order_usdt_size_rounds_base_quantity_down():
    instrument = Instrument("ETHUSDT", 3, 2, Decimal("0.001"), Decimal("1000"), 1, 125)
    order, notional, *_ = validate_test_order("ETHUSDT", "LONG", "10", "3333.00", "3000.00", "3999.00", 2, "1000", instrument)

    assert order.quantity == Decimal("0.003")
    assert notional == Decimal("9.99900")
    assert notional <= Decimal("10")


def test_one_way_consent_changes_and_verifies_account(monkeypatch):
    class Client:
        changed = []

        def change_position_mode(self, mode):
            self.changed.append(mode)

        def get_account(self, _coin):
            return {"positionMode": "ONE_WAY"}

    client = Client()
    logs = []
    window = SimpleNamespace(
        controller=SimpleNamespace(client=client),
        append_log=lambda category, message: logs.append((category, message)),
    )
    monkeypatch.setattr(
        main_window_module,
        "PositionModeConfirmation",
        lambda _parent: SimpleNamespace(exec=lambda: QDialog.Accepted),
    )

    assert MainWindow._ensure_one_way_mode(window, "HEDGE") is True
    assert client.changed == ["ONE_WAY"]
    assert logs


def test_cancelled_one_way_consent_does_not_mutate_account(monkeypatch):
    client = SimpleNamespace(change_position_mode=lambda _mode: (_ for _ in ()).throw(AssertionError("must not change")))
    window = SimpleNamespace(controller=SimpleNamespace(client=client))
    monkeypatch.setattr(
        main_window_module,
        "PositionModeConfirmation",
        lambda _parent: SimpleNamespace(exec=lambda: QDialog.Rejected),
    )

    assert MainWindow._ensure_one_way_mode(window, "HEDGE") is False


def test_live_symbol_settings_change_only_after_consent_and_are_verified(monkeypatch):
    class Client:
        state = {"leverage": 5, "marginMode": "CROSS"}

        def get_leverage_margin_mode(self, _symbol):
            return dict(self.state)

        def change_leverage(self, _symbol, value):
            self.state["leverage"] = value

        def change_margin_mode(self, _symbol, value):
            self.state["marginMode"] = value

    client = Client()
    settings = SimpleNamespace(symbol="BTCUSDT", leverage=2, margin_mode="ISOLATION")
    window = SimpleNamespace(controller=SimpleNamespace(client=client, settings=settings), append_log=lambda *_args: None)
    monkeypatch.setattr(
        main_window_module,
        "AccountSettingsConfirmation",
        lambda *_args: SimpleNamespace(exec=lambda: QDialog.Accepted),
    )

    assert MainWindow._ensure_live_symbol_settings(window) is True
    assert client.state == {"leverage": 2, "marginMode": "ISOLATION"}


def test_stale_codexbot_orders_are_cancelled_but_external_orders_block_start(monkeypatch):
    class Client:
        pending = [{"orderId": "1", "symbol": "BTCUSDT", "clientId": "cb-old"}]

        def get_positions(self, _symbol):
            return []

        def get_pending_orders(self, _symbol):
            return list(self.pending)

    client = Client()
    trading = SimpleNamespace(
        is_codexbot_order=lambda order: order["clientId"].startswith("cb"),
        cancel_owned_pending_orders=lambda **_kwargs: 1,
    )
    window = SimpleNamespace(
        controller=SimpleNamespace(client=client, trading=trading, settings=SimpleNamespace(symbol="BTCUSDT")),
        append_log=lambda *_args: None,
    )
    monkeypatch.setattr(
        main_window_module,
        "PendingOrdersConfirmation",
        lambda *_args: SimpleNamespace(exec=lambda: QDialog.Accepted),
    )
    assert MainWindow._clear_live_start_conflicts(window) is True

    client.pending = [{"orderId": "2", "symbol": "BTCUSDT", "clientId": "manual"}]
    try:
        MainWindow._clear_live_start_conflicts(window)
    except ValueError as exc:
        assert "non-CodexBot" in str(exc)
    else:
        raise AssertionError("external pending order must block Live startup")


def test_live_stop_cancels_owned_orders_only_after_consent(monkeypatch):
    calls = []
    trading = SimpleNamespace(
        state=SimpleNamespace(state=AppState.RUNNING_LIVE),
        get_owned_pending_orders=lambda **_kwargs: [{"orderId": "1"}],
        get_live_positions=lambda **_kwargs: [object()],
        stop=lambda **kwargs: calls.append(kwargs),
    )
    window = SimpleNamespace(controller=SimpleNamespace(trading=trading), append_log=lambda *_args: None)
    monkeypatch.setattr(
        main_window_module,
        "LiveStopConfirmation",
        lambda *_args: SimpleNamespace(
            exec=lambda: QDialog.Accepted,
            close_positions=SimpleNamespace(isChecked=lambda: False),
        ),
    )

    assert MainWindow._stop_trading_with_consent(window) is True
    assert calls == [{"cancel_owned_orders": True, "close_positions": False}]


def test_live_stop_closes_open_positions_only_when_selected(monkeypatch):
    calls = []
    trading = SimpleNamespace(
        state=SimpleNamespace(state=AppState.RUNNING_LIVE),
        get_owned_pending_orders=lambda **_kwargs: [],
        get_live_positions=lambda **_kwargs: [object(), object()],
        stop=lambda **kwargs: calls.append(kwargs),
    )
    window = SimpleNamespace(controller=SimpleNamespace(trading=trading), append_log=lambda *_args: None)
    monkeypatch.setattr(
        main_window_module,
        "LiveStopConfirmation",
        lambda *_args: SimpleNamespace(
            exec=lambda: QDialog.Accepted,
            close_positions=SimpleNamespace(isChecked=lambda: True),
        ),
    )

    assert MainWindow._stop_trading_with_consent(window) is True
    assert calls == [{"cancel_owned_orders": False, "close_positions": True}]


def test_live_dashboard_uses_cached_bitunix_values():
    _app = QApplication.instance() or QApplication([])
    card_names = ["Connection", "Mode", "Symbol", "Market Price", "Balance", "Available", "Unrealized PnL", "Realized PnL", "Strategy", "HTF Trend", "Signal", "Open Position", "Bot State"]
    cards = {name: QLabel() for name in card_names}
    trading = SimpleNamespace(
        rest_connected=True, public_websocket_connected=True, private_websocket_connected=True,
        last_price=100, live_account={"available": "100", "frozen": "5", "margin": "10", "crossUnrealizedPNL": "2", "isolationUnrealizedPNL": "1"},
        live_positions=[object()], strategy_name="SP2L", current_trend="BULLISH", current_signal="LONG",
        state=SimpleNamespace(state=AppState.RUNNING_LIVE), live_state_updated_at=None,
    )
    window = SimpleNamespace(
        controller=SimpleNamespace(settings=SimpleNamespace(symbol="BTCUSDT"), trading=trading),
        mode=SimpleNamespace(currentText=lambda: "LIVE"), cards=cards,
    )

    MainWindow.refresh_dashboard(window)

    assert cards["Balance"].text() == "$115.00"
    assert cards["Available"].text() == "$100.00"
    assert cards["Unrealized PnL"].text() == "$3.00"
    assert cards["Open Position"].text() == "1"
    assert "PRIVATE WS" in cards["Connection"].text()
