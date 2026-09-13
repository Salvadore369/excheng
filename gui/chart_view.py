from __future__ import annotations

from math import floor

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPicture, QPainter


CHART_BACKGROUND = "#131722"
TEXT_COLOR = "#b2b5be"
UP_COLOR = "#089981"
DOWN_COLOR = "#f23645"


class IndexDateAxis(pg.AxisItem):
    """TradingView-style time axis backed by candle indexes."""

    def __init__(self, orientation: str = "bottom") -> None:
        super().__init__(orientation=orientation)
        self.timestamps: list[pd.Timestamp] = []

    def set_timestamps(self, values) -> None:
        self.timestamps = list(pd.to_datetime(values, utc=True)) if values is not None else []

    def tickStrings(self, values, scale, spacing):
        labels = []
        for value in values:
            index = int(round(value))
            if index < 0 or index >= len(self.timestamps):
                labels.append("")
                continue
            stamp = self.timestamps[index]
            if spacing >= 48:
                labels.append(stamp.strftime("%d %b"))
            elif spacing >= 8:
                labels.append(stamp.strftime("%d %b %H:%M"))
            else:
                labels.append(stamp.strftime("%H:%M"))
        return labels


class CandlestickItem(pg.GraphicsObject):
    def __init__(self, frame: pd.DataFrame) -> None:
        super().__init__()
        self.picture = QPicture()
        self._bounds = QRectF()
        self._generate(frame)

    def _generate(self, frame: pd.DataFrame) -> None:
        painter = QPainter(self.picture)
        painter.setRenderHint(QPainter.Antialiasing, False)
        body_half_width = 0.36
        minimum_body = max(float(frame.high.max() - frame.low.min()) * 0.00008, 1e-9)
        for index, row in frame.reset_index(drop=True).iterrows():
            open_, high, low, close = map(float, (row.open, row.high, row.low, row.close))
            color = UP_COLOR if close >= open_ else DOWN_COLOR
            painter.setPen(pg.mkPen(color, width=1))
            painter.drawLine(index, low, index, high)
            painter.setBrush(pg.mkBrush(color))
            painter.drawRect(QRectF(index-body_half_width, min(open_, close), body_half_width*2, max(abs(close-open_), minimum_body)))
        painter.end()
        if not frame.empty:
            low, high = float(frame.low.min()), float(frame.high.max())
            self._bounds = QRectF(-0.5, low, max(len(frame), 1), max(high-low, 1e-9))

    def paint(self, painter, option, widget=None):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return self._bounds


class MarketChart(pg.GraphicsLayoutWidget):
    """Interactive candlestick chart with TradingView-inspired behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.setBackground(CHART_BACKGROUND)
        self.ci.setContentsMargins(0, 0, 0, 0)
        self._frame = pd.DataFrame()
        self._symbol = "MARKET"
        self._timeframe = ""

        self.legend_label = pg.LabelItem(justify="left")
        self.addItem(self.legend_label, row=0, col=0)
        self.price_axis = IndexDateAxis("bottom")
        self.price_plot = self.addPlot(row=1, col=0, axisItems={"bottom": self.price_axis})
        self.volume_axis = IndexDateAxis("bottom")
        self.volume_plot = self.addPlot(row=2, col=0, axisItems={"bottom": self.volume_axis})
        self.ci.layout.setRowStretchFactor(1, 5)
        self.ci.layout.setRowStretchFactor(2, 1)
        self.volume_plot.setMaximumHeight(150)
        self.volume_plot.setXLink(self.price_plot)
        self._style_plot(self.price_plot)
        self._style_plot(self.volume_plot)
        self.price_plot.hideAxis("bottom")
        self.volume_plot.getAxis("right").setStyle(showValues=False)
        self.volume_plot.getAxis("right").setWidth(72)

        dash_pen = pg.mkPen("#758696", width=1, style=Qt.DashLine)
        self.crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=dash_pen)
        self.crosshair_h = pg.InfiniteLine(angle=0, movable=False, pen=dash_pen)
        self.volume_crosshair_v = pg.InfiniteLine(angle=90, movable=False, pen=dash_pen)
        for item in (self.crosshair_v, self.crosshair_h):
            self.price_plot.addItem(item, ignoreBounds=True)
            item.hide()
        self.volume_plot.addItem(self.volume_crosshair_v, ignoreBounds=True)
        self.volume_crosshair_v.hide()

        self.watermark = pg.TextItem("MARKET", color=(120, 123, 134, 36), anchor=(0.5, 0.5))
        self.watermark.setFont(QFont("Segoe UI", 28, 700))
        self.price_plot.addItem(self.watermark, ignoreBounds=True)
        self._mouse_proxy = pg.SignalProxy(self.scene().sigMouseMoved, rateLimit=60, slot=self._mouse_moved)
        self._update_header()

    @staticmethod
    def _style_plot(plot) -> None:
        plot.setMenuEnabled(False)
        plot.setClipToView(True)
        plot.showGrid(x=True, y=True, alpha=0.22)
        plot.getViewBox().setMouseEnabled(x=True, y=True)
        plot.getViewBox().setDefaultPadding(0.04)
        plot.hideButtons()
        plot.setDownsampling(mode="peak")
        plot.getAxis("bottom").setPen(pg.mkPen("#2a2e39"))
        plot.getAxis("bottom").setTextPen(pg.mkPen(TEXT_COLOR))
        plot.getAxis("bottom").setStyle(tickLength=-4)
        plot.hideAxis("left")
        plot.showAxis("right")
        plot.getAxis("right").setPen(pg.mkPen("#2a2e39"))
        plot.getAxis("right").setTextPen(pg.mkPen(TEXT_COLOR))
        plot.getAxis("right").setStyle(tickLength=-4)
        plot.getAxis("right").setWidth(72)

    def set_market(self, symbol: str, timeframe: str) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._update_header()

    def reset_view(self) -> None:
        self.price_plot.enableAutoRange()
        self.volume_plot.enableAutoRange()

    def set_candles(self, frame: pd.DataFrame, trades=None) -> None:
        self._clear_data_items()
        self.volume_plot.show()
        self.price_plot.hideAxis("bottom")
        self.price_plot.getAxis("right").setLabel("")
        if frame.empty:
            self._frame = pd.DataFrame()
            self._update_header()
            return
        self._frame = frame.tail(500).reset_index(drop=True).copy()
        view = self._frame
        timestamps = view["timestamp"] if "timestamp" in view else None
        self.price_axis.set_timestamps(timestamps)
        self.volume_axis.set_timestamps(timestamps)
        self.price_plot.addItem(CandlestickItem(view))

        if "volume" in view:
            volumes = view["volume"].astype(float).to_numpy()
            brushes = [pg.mkBrush(UP_COLOR if row.close >= row.open else "#f23645b0") for row in view.itertuples()]
            self.volume_plot.addItem(pg.BarGraphItem(x=list(range(len(view))), height=volumes, width=0.72, brushes=brushes, pen=None))
            self.volume_plot.setYRange(0, max(volumes.max()*4.2, 1), padding=0)
        if "ema_fast" in view:
            self.price_plot.plot(view.index, view["ema_fast"], pen=pg.mkPen("#2962ff", width=1.4))
        if "ema_slow" in view:
            self.price_plot.plot(view.index, view["ema_slow"], pen=pg.mkPen("#ff9800", width=1.4))
        self._add_trades(view, trades)

        last_close = float(view.close.iloc[-1])
        last_color = UP_COLOR if view.close.iloc[-1] >= view.open.iloc[-1] else DOWN_COLOR
        self.price_plot.addItem(pg.InfiniteLine(angle=0, pos=last_close, pen=pg.mkPen(last_color, width=1, style=Qt.DashLine)))
        self.watermark.setText(f"{self._symbol}  ·  {self._timeframe}")
        self.watermark.setPos((len(view)-1)/2, (float(view.low.min())+float(view.high.max()))/2)
        self.price_plot.setXRange(max(0, len(view)-150), len(view)+3, padding=0)
        self.price_plot.enableAutoRange(axis="y")
        self._update_header(len(view)-1)

    def _clear_data_items(self) -> None:
        for item in list(self.price_plot.items):
            if item not in {self.crosshair_v, self.crosshair_h, self.watermark}:
                self.price_plot.removeItem(item)
        for item in list(self.volume_plot.items):
            if item is not self.volume_crosshair_v:
                self.volume_plot.removeItem(item)

    def _add_trades(self, view: pd.DataFrame, trades) -> None:
        if not trades or "timestamp" not in view:
            return
        timestamps = pd.to_datetime(view["timestamp"], utc=True)
        entries, exits = [], []
        for trade in trades:
            entry_at, exit_at = pd.Timestamp(trade.entry_time), pd.Timestamp(trade.exit_time)
            if entry_at < timestamps.iloc[0] or entry_at > timestamps.iloc[-1]:
                continue
            entry_index = int((timestamps-entry_at).abs().argmin())
            exit_index = int((timestamps-exit_at).abs().argmin())
            is_long = trade.direction.value == "LONG"
            entries.append({"pos":(entry_index,float(trade.entry_price)),"symbol":"t1" if is_long else "t","brush":UP_COLOR if is_long else DOWN_COLOR})
            exits.append({"pos":(exit_index,float(trade.exit_price)),"symbol":"x","brush":"#d1d4dc"})
            self.price_plot.plot([entry_index,exit_index],[float(trade.stop_loss)]*2,pen=pg.mkPen(DOWN_COLOR,style=Qt.DashLine))
            self.price_plot.plot([entry_index,exit_index],[float(trade.take_profit)]*2,pen=pg.mkPen(UP_COLOR,style=Qt.DashLine))
        if entries:
            self.price_plot.addItem(pg.ScatterPlotItem(spots=entries,size=11,pen=pg.mkPen(None)))
        if exits:
            self.price_plot.addItem(pg.ScatterPlotItem(spots=exits,size=11,pen=pg.mkPen(None)))

    def _mouse_moved(self, event) -> None:
        position = event[0]
        if self.price_plot.sceneBoundingRect().contains(position) and not self._frame.empty:
            point = self.price_plot.getViewBox().mapSceneToView(position)
            index = max(0, min(len(self._frame)-1, floor(point.x()+0.5)))
            self.crosshair_v.setPos(index)
            self.crosshair_h.setPos(point.y())
            self.volume_crosshair_v.setPos(index)
            self.crosshair_v.show(); self.crosshair_h.show(); self.volume_crosshair_v.show()
            self._update_header(index)
        else:
            self.crosshair_v.hide(); self.crosshair_h.hide(); self.volume_crosshair_v.hide()

    def _update_header(self, index: int | None = None) -> None:
        market = f"{self._symbol} · {self._timeframe}".strip(" ·")
        if index is None or self._frame.empty:
            self.legend_label.setText(f"<span style='color:#d1d4dc;font-size:12px;font-weight:600'>{market}</span>")
            return
        row = self._frame.iloc[index]
        color = UP_COLOR if float(row.close) >= float(row.open) else DOWN_COLOR
        volume = f"  Vol <span style='color:{TEXT_COLOR}'>{float(row.get('volume',0)):,.4g}</span>" if "volume" in self._frame else ""
        self.legend_label.setText(
            f"<span style='color:#d1d4dc;font-weight:600'>{market}</span>  "
            f"<span style='color:{TEXT_COLOR}'>O</span> <span style='color:{color}'>{float(row.open):,.8g}</span>  "
            f"<span style='color:{TEXT_COLOR}'>H</span> <span style='color:{color}'>{float(row.high):,.8g}</span>  "
            f"<span style='color:{TEXT_COLOR}'>L</span> <span style='color:{color}'>{float(row.low):,.8g}</span>  "
            f"<span style='color:{TEXT_COLOR}'>C</span> <span style='color:{color}'>{float(row.close):,.8g}</span>{volume}"
        )

    def set_equity(self, curve) -> None:
        self._clear_data_items()
        self._frame = pd.DataFrame()
        self.volume_plot.hide()
        self.price_plot.showAxis("bottom")
        self.price_plot.getAxis("right").setLabel("Equity", color=TEXT_COLOR)
        self.watermark.setText("EQUITY CURVE")
        if curve:
            values = [float(value) for _, value in curve]
            self.price_plot.plot(range(len(values)), values, pen=pg.mkPen("#2962ff", width=2), fillLevel=min(values), brush=pg.mkBrush(41,98,255,35))
            self.watermark.setPos((len(values)-1)/2, (min(values)+max(values))/2)
            self.price_plot.enableAutoRange()
        self.legend_label.setText("<span style='color:#d1d4dc;font-weight:600'>STRATEGY EQUITY</span>")
