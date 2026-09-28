import hashlib
import hmac
import json
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


load_dotenv()


class DeltaClient:
    def __init__(self):
        self.api_key = os.getenv("DELTA_API_KEY")
        self.api_secret = os.getenv("DELTA_API_SECRET")
        self.symbol = os.getenv("DELTA_SYMBOL", "BTCUSD")

        self.allow_orders = (
            os.getenv("DELTA_ALLOW_ORDERS", "false").lower() == "true"
        )

        self.testnet = (
            os.getenv("DELTA_TESTNET", "false").lower() == "true"
        )

        if self.testnet:
            self.base_url = "https://cdn-ind.testnet.deltaex.org"
            self.environment = "INDIA TESTNET"
        else:
            self.base_url = "https://api.india.delta.exchange"
            self.environment = "INDIA PRODUCTION"

        if not self.api_key:
            raise RuntimeError("DELTA_API_KEY missing.")

        if not self.api_secret:
            raise RuntimeError("DELTA_API_SECRET missing.")

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ScalpBot-Python",
        })

        print("\n🔗 DELTA CLIENT")
        print(f"Environment : {self.environment}")
        print(f"Base URL    : {self.base_url}")
        print(f"Orders      : {'ENABLED' if self.allow_orders else 'DISABLED'}")

    def _signature(self, method, timestamp, path, query_string="", body=""):
        message = method + timestamp + path + query_string + body

        return hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(
        self,
        method,
        path,
        params=None,
        body=None,
        authenticated=True,
    ):
        method = method.upper()
        params = params or {}

        query_string = ""
        if params:
            query_string = "?" + urlencode(params)

        body_text = ""
        if body is not None:
            body_text = json.dumps(body, separators=(",", ":"))

        url = self.base_url + path + query_string
        headers = {}

        if authenticated:
            timestamp = str(int(time.time()))

            signature = self._signature(
                method=method,
                timestamp=timestamp,
                path=path,
                query_string=query_string,
                body=body_text,
            )

            headers.update({
                "api-key": self.api_key,
                "signature": signature,
                "timestamp": timestamp,
            })

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                data=body_text if body_text else None,
                timeout=15,
            )
        except requests.RequestException as error:
            raise RuntimeError(f"Delta connection error: {error}")

        try:
            payload = response.json()
        except Exception:
            raise RuntimeError(
                f"Delta returned non-JSON: "
                f"{response.status_code} {response.text}"
            )

        if not response.ok:
            raise RuntimeError(
                f"Delta HTTP {response.status_code}: {payload}"
            )

        if (
            isinstance(payload, dict)
            and payload.get("success") is False
        ):
            raise RuntimeError(f"Delta API error: {payload}")

        return payload

    def get_product(self, symbol=None):
        symbol = symbol or self.symbol

        payload = self._request(
            method="GET",
            path=f"/v2/products/{symbol}",
            authenticated=False,
        )

        return payload["result"]

    def get_position(self, product_id):
        payload = self._request(
            method="GET",
            path="/v2/positions",
            params={"product_id": product_id},
            authenticated=True,
        )

        return payload["result"]

    def get_wallet_balances(self):
        return self._request(
            method="GET",
            path="/v2/wallet/balances",
            authenticated=True,
        )

    def set_leverage(self, product_id, leverage):
        if not self.allow_orders:
            raise RuntimeError("Order actions disabled.")

        payload = self._request(
            method="POST",
            path=f"/v2/products/{product_id}/orders/leverage",
            body={"leverage": str(leverage)},
            authenticated=True,
        )

        return payload["result"]

    def place_order(self, body):
        if not self.allow_orders:
            raise RuntimeError("Order actions disabled.")

        payload = self._request(
            method="POST",
            path="/v2/orders",
            body=body,
            authenticated=True,
        )

        return payload["result"]

    def place_market_order(
        self,
        product_id,
        size,
        side,
        client_order_id,
        reduce_only=False,
    ):
        return self.place_order({
            "product_id": int(product_id),
            "size": int(size),
            "side": side,
            "order_type": "market_order",
            "reduce_only": bool(reduce_only),
            "client_order_id": client_order_id,
        })

    def place_limit_order(
        self,
        product_id,
        size,
        side,
        limit_price,
        client_order_id,
        reduce_only=False,
        time_in_force="gtc",
        post_only=False,
    ):
        return self.place_order({
            "product_id": int(product_id),
            "size": int(size),
            "side": side,
            "order_type": "limit_order",
            "limit_price": str(limit_price),
            "time_in_force": time_in_force,
            "post_only": bool(post_only),
            "reduce_only": bool(reduce_only),
            "client_order_id": client_order_id,
        })

    def place_stop_market(
        self,
        product_id,
        size,
        side,
        stop_price,
        client_order_id,
    ):
        return self.place_order({
            "product_id": int(product_id),
            "size": int(size),
            "side": side,
            "order_type": "market_order",
            "stop_order_type": "stop_loss_order",
            "stop_price": str(stop_price),
            "stop_trigger_method": "last_traded_price",
            "reduce_only": True,
            "client_order_id": client_order_id,
        })

    def edit_stop_order(
        self,
        order_id,
        product_id,
        new_stop_price,
    ):
        if not self.allow_orders:
            raise RuntimeError("Order actions disabled.")

        body = {
            "id": int(order_id),
            "product_id": int(product_id),
            "stop_price": str(new_stop_price),
        }

        payload = self._request(
            method="PUT",
            path="/v2/orders",
            body=body,
            authenticated=True,
        )

        return payload["result"]

    def cancel_order(self, order_id, product_id):
        if not self.allow_orders:
            raise RuntimeError("Order actions disabled.")

        return self._request(
            method="DELETE",
            path="/v2/orders",
            body={
                "id": int(order_id),
                "product_id": int(product_id),
            },
            authenticated=True,
        )

    def get_order_by_client_id(self, client_order_id):
        payload = self._request(
            method="GET",
            path=f"/v2/orders/client_order_id/{client_order_id}",
            authenticated=True,
        )

        return payload["result"]

    @staticmethod
    def round_to_tick(price, tick_size):
        price = Decimal(str(price))
        tick = Decimal(str(tick_size))

        steps = (price / tick).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )

        return steps * tick
