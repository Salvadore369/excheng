import hashlib
import json
import asyncio
from decimal import Decimal

import httpx
import pytest

import execution.bitunix_client as bitunix_module
from execution.bitunix_client import BitunixClient, BitunixWebSocket, compact_json, sign_request, sign_websocket_login
from execution.base_exchange import ExchangeError, TemporaryExchangeError
from models.domain import Direction, Order, OrderSide


def test_exchange_request_signing_official_algorithm():
    nonce,timestamp,key,secret="123456","20241120123045","yourApiKey","yourSecretKey"; params={"uid":200,"id":1}; body={"uid":"2899"}
    digest=hashlib.sha256((nonce+timestamp+key+"id1uid200"+compact_json(body)).encode()).hexdigest(); expected=hashlib.sha256((digest+secret).encode()).hexdigest()
    assert sign_request(nonce,timestamp,key,secret,params,body)==expected


def test_private_websocket_signing_excludes_rest_parameters():
    nonce, timestamp, key, secret = "abc", "1732519687", "key", "secret"
    first = hashlib.sha256((nonce + timestamp + key).encode()).hexdigest()
    expected = hashlib.sha256((first + secret).encode()).hexdigest()
    assert sign_websocket_login(nonce, timestamp, key, secret) == expected


def test_exchange_response_parsing_and_order_construction():
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.path.endswith("trading_pairs"):
            data=[{"symbol":"BTCUSDT","basePrecision":4,"quotePrecision":1,"minTradeVolume":"0.0001","maxMarketOrderVolume":"50000","minLeverage":1,"maxLeverage":125,"symbolStatus":"OPEN","isApiSupported":True}]
        else: data={"orderId":"42","clientId":"abc"}
        return httpx.Response(200,json={"code":0,"data":data,"msg":"Success"})
    client=BitunixClient("key","secret",transport=httpx.MockTransport(handler)); instrument=client.get_instrument("BTCUSDT"); assert instrument.base_precision==4 and instrument.min_trade_volume==Decimal("0.0001")
    order=client.place_order(Order("BTCUSDT",OrderSide.BUY,Decimal("0.1"),stop_loss=Decimal("90"),take_profit=Decimal("120"))); assert order.id=="42"
    body=json.loads(requests[-1].content); assert body["side"]=="BUY" and body["slOrderType"]=="MARKET" and requests[-1].headers["api-key"]=="key"


def test_account_array_is_normalized_and_credentials_never_enter_errors():
    def handler(request):
        assert request.headers["api-key"] == "public-key"
        return httpx.Response(200,json={"code":0,"data":[{"marginCoin":"USDT","available":"10","positionMode":"ONE_WAY"}],"msg":"Success"})
    client=BitunixClient("public-key","super-secret",transport=httpx.MockTransport(handler))
    assert client.get_account()["available"]=="10"
    rejected=BitunixClient("public-key","super-secret",transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"code":1001,"data":None,"msg":"bad super-secret"})))
    with pytest.raises(ExchangeError) as error:
        rejected.get_account()
    assert "super-secret" not in str(error.value) and "[REDACTED]" in str(error.value)


def test_malformed_and_temporary_exchange_responses_are_bounded():
    attempts=0
    def temporary(request):
        nonlocal attempts; attempts+=1
        return httpx.Response(429,json={"code":1,"msg":"slow down"})
    client=BitunixClient(retries=2,transport=httpx.MockTransport(temporary))
    with pytest.raises(TemporaryExchangeError): client.get_tickers("BTCUSDT")
    assert attempts==2
    malformed=BitunixClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,text="not-json")))
    with pytest.raises(ExchangeError,match="malformed JSON"): malformed.get_tickers("BTCUSDT")


def test_live_order_precision_is_validated_before_post():
    post_called=False
    def handler(request):
        nonlocal post_called
        if request.url.path.endswith("trading_pairs"):
            return httpx.Response(200,json={"code":0,"data":[{"symbol":"BTCUSDT","basePrecision":3,"quotePrecision":1,"minTradeVolume":"0.001","maxMarketOrderVolume":"10","minLeverage":1,"maxLeverage":20,"symbolStatus":"OPEN","isApiSupported":True}]})
        post_called=True
        return httpx.Response(200,json={"code":0,"data":{"orderId":"1"}})
    client=BitunixClient("key","secret",transport=httpx.MockTransport(handler))
    with pytest.raises(ExchangeError,match="at most 3 decimals"):
        client.place_order(Order("BTCUSDT",OrderSide.BUY,Decimal("0.0001")))
    assert not post_called


def test_cancel_uses_per_order_success_list():
    def handler(request):
        data={"successList":[{"orderId":"42"}],"failureList":[]}
        return httpx.Response(200,json={"code":0,"data":data,"msg":"Success"})
    client=BitunixClient("key","secret",transport=httpx.MockTransport(handler))
    assert client.cancel_order("BTCUSDT","42") is True
    assert client.cancel_order("BTCUSDT","99") is False


def test_pending_orders_are_normalized():
    def handler(request):
        assert request.url.params["symbol"] == "BTCUSDT"
        data = {"orderList": [{"orderId": "42", "status": "NEW"}], "total": 1}
        return httpx.Response(200, json={"code": 0, "data": data, "msg": "Success"})

    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))
    assert client.get_pending_orders("BTCUSDT") == [{"orderId": "42", "status": "NEW"}]


@pytest.mark.parametrize(
    ("exchange_side", "expected_direction"),
    [
        ("BUY", Direction.LONG),
        ("SELL", Direction.SHORT),
        ("LONG", Direction.LONG),
        ("SHORT", Direction.SHORT),
    ],
)
def test_position_sides_are_normalized(exchange_side, expected_direction):
    def handler(_request):
        data = [{
            "symbol": "BTCUSDT", "side": exchange_side, "qty": "0.01",
            "avgOpenPrice": "100", "ctime": "1736121600000", "fee": "0.02",
            "positionId": "position-1",
        }]
        return httpx.Response(200, json={"code": 0, "data": data, "msg": "Success"})

    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))
    position = client.get_positions("BTCUSDT")[0]

    assert position.direction == expected_direction


def test_unknown_position_side_is_reported_as_exchange_data_error():
    def handler(_request):
        data = [{
            "symbol": "BTCUSDT", "side": "CROSS", "qty": "0.01",
            "avgOpenPrice": "100", "ctime": "1736121600000", "positionId": "position-1",
        }]
        return httpx.Response(200, json={"code": 0, "data": data, "msg": "Success"})

    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))

    with pytest.raises(ExchangeError, match="Malformed Bitunix position side: CROSS"):
        client.get_positions("BTCUSDT")


def test_position_mode_change_uses_official_account_endpoint_and_confirms_result():
    requests = []

    def handler(request):
        requests.append(request)
        data = [{"positionMode": "ONE_WAY"}]
        return httpx.Response(200, json={"code": 0, "data": data, "msg": "Success"})

    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))
    assert client.change_position_mode("ONE_WAY") == "ONE_WAY"
    assert requests[0].url.path.endswith("/account/change_position_mode")
    assert json.loads(requests[0].content) == {"positionMode": "ONE_WAY"}


def test_position_mode_change_rejects_unconfirmed_response():
    handler = lambda _request: httpx.Response(200, json={"code": 0, "data": [], "msg": "Success"})
    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))
    with pytest.raises(ExchangeError, match="did not confirm"):
        client.change_position_mode("ONE_WAY")


def test_leverage_and_margin_mode_are_read_changed_and_confirmed():
    def handler(request):
        if request.method == "GET":
            data = {"symbol": "BTCUSDT", "leverage": 2, "marginMode": "ISOLATION"}
        elif request.url.path.endswith("change_leverage"):
            data = [{"symbol": "BTCUSDT", "leverage": 3}]
        else:
            data = [{"symbol": "BTCUSDT", "marginMode": "CROSS"}]
        return httpx.Response(200, json={"code": 0, "data": data, "msg": "Success"})

    client = BitunixClient("key", "secret", transport=httpx.MockTransport(handler))
    assert client.get_leverage_margin_mode("BTCUSDT")["leverage"] == 2
    assert client.change_leverage("BTCUSDT", 3)["leverage"] == 3
    assert client.change_margin_mode("BTCUSDT", "CROSS")["marginMode"] == "CROSS"


def test_private_websocket_login_uses_seconds_and_reports_connected(monkeypatch):
    class Socket:
        def __init__(self):
            self.sent = []
            self.responses = [
                {"op": "connect", "data": "connected"},
                {"op": "login", "data": {"result": True}},
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send(self, message):
            self.sent.append(json.loads(message))

        async def recv(self):
            return json.dumps(self.responses.pop(0))

    socket = Socket()
    monkeypatch.setattr(bitunix_module.websockets, "connect", lambda *_args, **_kwargs: socket)
    monkeypatch.setattr(bitunix_module.time, "time", lambda: 1_732_519_687.9)
    monkeypatch.setattr(bitunix_module.secrets, "token_hex", lambda _size: "nonce")
    stream = BitunixWebSocket("key", "secret")
    statuses = []

    async def handler(message):
        statuses.append(message)
        if message.get("status") == "connected":
            stream.stop()

    asyncio.run(stream.run([{"ch": "order"}], handler, private=True))

    login = socket.sent[0]["args"][0]
    assert login["timestamp"] == 1_732_519_687
    assert login["sign"] == sign_websocket_login("nonce", "1732519687", "key", "secret")
    assert socket.sent[1] == {"op": "subscribe", "args": [{"ch": "order"}]}
    assert any(status.get("status") == "connected" for status in statuses)


def test_public_websocket_sends_heartbeat_during_continuous_market_traffic(monkeypatch):
    class Socket:
        def __init__(self):
            self.sent = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def send(self, message):
            self.sent.append(json.loads(message))

        async def recv(self):
            return json.dumps({"ch": "ticker", "data": {"lastPrice": "100"}})

    socket = Socket()
    monkeypatch.setattr(bitunix_module.websockets, "connect", lambda *_args, **_kwargs: socket)
    stream = BitunixWebSocket()
    stream.HEARTBEAT_INTERVAL_SECONDS = 0
    messages = []

    async def handler(message):
        messages.append(message)
        if message.get("ch") == "ticker":
            stream.stop()

    asyncio.run(stream.run([{"symbol": "BTCUSDT", "ch": "ticker"}], handler))

    assert socket.sent[0]["op"] == "subscribe"
    assert any(frame.get("op") == "ping" for frame in socket.sent)
    assert any(message.get("ch") == "ticker" for message in messages)
