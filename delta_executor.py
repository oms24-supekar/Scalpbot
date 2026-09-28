import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class DeltaExecutor:
    """
    Live BTCUSD executor.

    Entry:
      LONG  -> buy limit at signal price + entry_limit_offset
      SHORT -> sell limit at signal price - entry_limit_offset

    The entry is IOC, not GTC. If it cannot fill immediately within the
    allowed price cap, the remaining quantity is cancelled.

    Protection:
      Initial SL remains STOP-MARKET deliberately.
      6R target is a resting reduce-only LIMIT order.
    """

    def __init__(
        self,
        client,
        symbol="BTCUSD",
        contracts_per_trade=1,
        risk_dollars=1.0,
        entry_limit_offset=12.5,
        session_start_hour=0,
        session_end_hour=24,
        allowed_entry_hours=None,
        max_entries_per_day=2,
        final_target_r=6.0,
        max_contracts=1,
        max_daily_loss_usd=2.0,
        live_auto_trading=False,
    ):
        self.client = client
        self.symbol = symbol

        self.contracts_per_trade = int(contracts_per_trade)
        self.risk_dollars = float(risk_dollars)
        self.entry_limit_offset = float(entry_limit_offset)

        self.session_start_hour = int(session_start_hour)
        self.session_end_hour = int(session_end_hour)
        self.allowed_entry_hours = (
            set(allowed_entry_hours)
            if allowed_entry_hours is not None
            else {10, 14}
        )
        self.max_entries_per_day = int(max_entries_per_day)
        self.final_target_r = float(final_target_r)

        self.max_contracts = int(max_contracts)
        self.max_daily_loss_usd = float(max_daily_loss_usd)
        self.live_auto_trading = bool(live_auto_trading)

        self.position = None
        self.entries_today = 0
        self.current_ist_date = None
        self.day_start_equity = None
        self.last_processed_candle = None
        self.kill_switch = False

        self.state_dir = "state"
        self.state_file = os.path.join(
            self.state_dir,
            "delta_live_state.json",
        )
        os.makedirs(self.state_dir, exist_ok=True)

        product = self.client.get_product(self.symbol)

        self.product_id = int(product["id"])
        self.contract_value = float(product["contract_value"])
        self.tick_size = float(product["tick_size"])

        self._load_state()
        self._ensure_day_state()

        print("\n🔐 LIVE EXECUTOR")
        print("=" * 60)
        print(f"Symbol              : {self.symbol}")
        print(f"Product ID          : {self.product_id}")
        print(f"Contract value      : {self.contract_value} BTC")
        print(f"Contracts/trade     : {self.contracts_per_trade}")
        print(f"Risk/trade          : ${self.risk_dollars:.2f}")
        print(f"Entry limit offset  : ${self.entry_limit_offset:.2f}")
        print(
            "Entry hours (IST)   : "
            + ", ".join(
                f"{hour:02d}:00-{hour:02d}:59"
                for hour in sorted(self.allowed_entry_hours)
            )
        )
        print(f"Max contracts       : {self.max_contracts}")
        print(f"Max entries/day     : {self.max_entries_per_day}")
        print(f"Daily loss cap      : ${self.max_daily_loss_usd:.2f}")
        print(f"Kill switch         : {'ON' if self.kill_switch else 'OFF'}")
        print(f"Live auto trading   : {'ON' if self.live_auto_trading else 'OFF'}")
        print("=" * 60)

    # ==================================================
    # STATE
    # ==================================================

    def _state_payload(self):
        return {
            "version": 1,
            "position": self.position,
            "entries_today": self.entries_today,
            "current_ist_date": (
                str(self.current_ist_date)
                if self.current_ist_date
                else None
            ),
            "day_start_equity": self.day_start_equity,
            "last_processed_candle": self.last_processed_candle,
            "kill_switch": self.kill_switch,
        }

    def _save_state(self):
        temp = self.state_file + ".tmp"

        with open(temp, "w", encoding="utf-8") as file:
            json.dump(
                self._state_payload(),
                file,
                indent=2,
            )

        os.replace(temp, self.state_file)

    def _load_state(self):
        if not os.path.exists(self.state_file):
            self._save_state()
            return

        try:
            with open(
                self.state_file,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            self.position = data.get("position")
            self.entries_today = int(data.get("entries_today", 0))
            self.day_start_equity = data.get("day_start_equity")
            self.last_processed_candle = data.get(
                "last_processed_candle"
            )
            self.kill_switch = bool(
                data.get("kill_switch", False)
            )

            saved_date = data.get("current_ist_date")
            if saved_date:
                self.current_ist_date = datetime.strptime(
                    saved_date,
                    "%Y-%m-%d",
                ).date()

        except Exception as error:
            raise RuntimeError(
                f"Could not load live state: {error}"
            )

    # ==================================================
    # WALLET
    # ==================================================

    def _wallet_snapshot(self):
        wallet = self.client.get_wallet_balances()

        net_equity = float(
            wallet.get("meta", {}).get("net_equity", 0)
            or 0
        )

        available = 0.0

        for asset in wallet.get("result", []):
            if asset.get("asset_symbol") == "USD":
                available = float(
                    asset.get("available_balance", 0)
                    or 0
                )
                break

        return net_equity, available

    # ==================================================
    # DAY / SESSION
    # ==================================================

    def _ensure_day_state(self):
        today = datetime.now(IST).date()

        if self.current_ist_date != today:
            net_equity, _ = self._wallet_snapshot()

            self.current_ist_date = today
            self.entries_today = 0
            self.day_start_equity = net_equity
            self._save_state()

        elif self.day_start_equity is None:
            net_equity, _ = self._wallet_snapshot()
            self.day_start_equity = net_equity
            self._save_state()

    def _get_ist_datetime(self, timestamp):
        return datetime.fromisoformat(
            timestamp
        ).astimezone(IST)

    def _update_day_from_candle(self, timestamp):
        candle_date = self._get_ist_datetime(
            timestamp
        ).date()

        if candle_date != self.current_ist_date:
            net_equity, _ = self._wallet_snapshot()

            self.current_ist_date = candle_date
            self.entries_today = 0
            self.day_start_equity = net_equity
            self._save_state()

    def _inside_session(self, timestamp):
        ist_dt = self._get_ist_datetime(
            timestamp
        )

        # FINAL ENTRY HOURS:
        # 10:00-10:59 IST and 14:00-14:59 IST.
        # Position management remains active 24/7.
        if self.allowed_entry_hours is not None:
            return (
                ist_dt.hour
                in self.allowed_entry_hours
            )

        return (
            self.session_start_hour
            <= ist_dt.hour
            < self.session_end_hour
        )

    # ==================================================
    # SAFETY
    # ==================================================

    def activate_kill_switch(self):
        self.kill_switch = True
        self._save_state()
        print("\n🛑 KILL SWITCH ACTIVATED")

    def deactivate_kill_switch(self):
        self.kill_switch = False
        self._save_state()
        print("\n✅ Kill switch disabled")

    def _safety_check(self, timestamp):
        self._update_day_from_candle(timestamp)

        if self.kill_switch:
            raise RuntimeError("Kill switch is active.")

        if not self.live_auto_trading:
            raise RuntimeError(
                "LIVE_AUTO_TRADING is disabled."
            )

        if not self.client.allow_orders:
            raise RuntimeError(
                "DELTA_ALLOW_ORDERS=false."
            )

        if not self._inside_session(timestamp):
            raise RuntimeError(
                "Signal is outside entry session."
            )

        if self.entries_today >= self.max_entries_per_day:
            raise RuntimeError(
                "Daily entry limit reached."
            )

        if self.contracts_per_trade < 1:
            raise RuntimeError(
                "contracts_per_trade must be >= 1."
            )

        if self.contracts_per_trade > self.max_contracts:
            raise RuntimeError(
                "Contract count exceeds hard cap."
            )

        exchange_position = self.client.get_position(
            self.product_id
        )

        exchange_size = int(
            exchange_position.get("size", 0)
            or 0
        )

        if exchange_size != 0:
            raise RuntimeError(
                f"Exchange already has BTCUSD "
                f"position size {exchange_size}."
            )

        net_equity, available = self._wallet_snapshot()

        daily_loss = max(
            0.0,
            float(self.day_start_equity or net_equity)
            - net_equity,
        )

        if daily_loss >= self.max_daily_loss_usd:
            raise RuntimeError(
                f"Daily loss cap reached: "
                f"${daily_loss:.2f}"
            )

        return net_equity, available

    # ==================================================
    # PRICE CALCULATIONS
    # ==================================================

    def _round_price(self, price):
        return float(
            self.client.round_to_tick(
                price,
                self.tick_size,
            )
        )

    def _entry_limit_price(self, side, signal_price):
        # Marketable limit:
        # LONG  = willing to pay up to signal + offset
        # SHORT = willing to sell down to signal - offset
        if side == "LONG":
            return self._round_price(
                signal_price + self.entry_limit_offset
            )

        return self._round_price(
            signal_price - self.entry_limit_offset
        )

    def _one_r_distance(self):
        btc_quantity = (
            self.contracts_per_trade
            * self.contract_value
        )

        return (
            self.risk_dollars
            / btc_quantity
        )

    def _price_at_r(
        self,
        side,
        entry,
        one_r_distance,
        multiple,
    ):
        if side == "LONG":
            price = (
                entry
                + one_r_distance * multiple
            )
        else:
            price = (
                entry
                - one_r_distance * multiple
            )

        return self._round_price(price)

    # ==================================================
    # ENTRY
    # ==================================================

    def open_trade(self, signal):
        if self.position is not None:
            print("⚠️ Local live position already exists.")
            return False

        timestamp = signal["timestamp"]

        try:
            net_equity, available = self._safety_check(
                timestamp
            )
        except Exception as error:
            print(f"\n🛡️ ENTRY BLOCKED: {error}")
            return False

        side = signal["side"]
        signal_price = float(signal["entry"])

        order_side = (
            "buy"
            if side == "LONG"
            else "sell"
        )

        exit_side = (
            "sell"
            if side == "LONG"
            else "buy"
        )

        limit_price = self._entry_limit_price(
            side,
            signal_price,
        )

        unique = str(int(time.time() * 1000))
        entry_client_id = f"ema-entry-{unique}"

        print("\n" + "=" * 60)
        print("⚡ LIVE ENTRY SIGNAL")
        print(f"Side           : {side}")
        print(f"Signal close   : {signal_price:.2f}")
        print(f"Limit cap      : {limit_price:.2f}")
        print(f"Contracts      : {self.contracts_per_trade}")
        print(f"Net equity     : ${net_equity:.2f}")
        print(f"Available USD  : ${available:.2f}")
        print("=" * 60)

        entry_order = self.client.place_limit_order(
            product_id=self.product_id,
            size=self.contracts_per_trade,
            side=order_side,
            limit_price=limit_price,
            client_order_id=entry_client_id,
            reduce_only=False,
            time_in_force="ioc",
            post_only=False,
        )

        time.sleep(0.8)

        try:
            entry_order = (
                self.client.get_order_by_client_id(
                    entry_client_id
                )
            )
        except Exception:
            pass

        filled_size = (
            self.contracts_per_trade
            - int(
                entry_order.get("unfilled_size", 0)
                or 0
            )
        )

        fill_price = entry_order.get(
            "average_fill_price"
        )

        if (
            entry_order.get("state") != "closed"
            or filled_size != self.contracts_per_trade
            or not fill_price
        ):
            print(
                "\n⚪ Entry not fully filled inside "
                "the limit cap. Signal skipped."
            )
            print(
                f"Order state   : "
                f"{entry_order.get('state')}"
            )
            print(
                f"Filled size   : "
                f"{filled_size}"
            )
            return False

        entry = float(fill_price)
        one_r_distance = self._one_r_distance()

        stop_price = self._price_at_r(
            side,
            entry,
            one_r_distance,
            -1.0,
        )

        target_price = self._price_at_r(
            side,
            entry,
            one_r_distance,
            self.final_target_r,
        )

        stop_client_id = f"ema-sl-{unique}"
        tp_client_id = f"ema-tp-{unique}"

        try:
            stop_order = self.client.place_stop_market(
                product_id=self.product_id,
                size=self.contracts_per_trade,
                side=exit_side,
                stop_price=stop_price,
                client_order_id=stop_client_id,
            )

            # TP is a reduce-only LIMIT order, not a market order.
            tp_order = self.client.place_limit_order(
                product_id=self.product_id,
                size=self.contracts_per_trade,
                side=exit_side,
                limit_price=target_price,
                client_order_id=tp_client_id,
                reduce_only=True,
                time_in_force="gtc",
                post_only=False,
            )

        except Exception as protection_error:
            print(
                "\n🚨 PROTECTION CREATION FAILED."
            )
            print(protection_error)

            # Emergency close uses reduce-only market because
            # leaving an unprotected live position is worse.
            try:
                self.client.place_market_order(
                    product_id=self.product_id,
                    size=self.contracts_per_trade,
                    side=exit_side,
                    client_order_id=f"ema-emergency-{unique}",
                    reduce_only=True,
                )
                print(
                    "🧯 Emergency reduce-only close sent."
                )
            finally:
                raise

        self.entries_today += 1

        self.position = {
            "side": side,
            "entry": entry,
            "entry_time": timestamp,
            "signal_price": signal_price,
            "entry_limit_price": limit_price,
            "contracts": self.contracts_per_trade,
            "btc_quantity": (
                self.contracts_per_trade
                * self.contract_value
            ),
            "risk_dollars": self.risk_dollars,
            "one_r_distance": one_r_distance,
            "stop_price": stop_price,
            "target_price": target_price,
            "protected_r": -1.0,
            "highest_r_reached": 0.0,
            "entry_order_id": entry_order.get("id"),
            "entry_client_id": entry_client_id,
            "stop_order_id": stop_order.get("id"),
            "stop_client_id": stop_client_id,
            "tp_order_id": tp_order.get("id"),
            "tp_client_id": tp_client_id,
        }

        self._save_state()

        print("\n✅ LIVE POSITION OPENED")
        print(f"Entry fill     : {entry:.2f}")
        print(f"Initial SL     : {stop_price:.2f}")
        print(f"6R TP limit    : {target_price:.2f}")
        print(f"1R distance    : {one_r_distance:.2f}")

        return True

    # ==================================================
    # STOP LADDER
    # ==================================================

    def _move_stop(self, protected_r):
        if not self.position:
            return

        p = self.position

        new_stop = self._price_at_r(
            p["side"],
            p["entry"],
            p["one_r_distance"],
            protected_r,
        )

        self.client.edit_stop_order(
            order_id=p["stop_order_id"],
            product_id=self.product_id,
            new_stop_price=new_stop,
        )

        p["stop_price"] = new_stop
        p["protected_r"] = protected_r

        self._save_state()

        print(
            f"🔒 Stop moved to "
            f"{protected_r:+.1f}R "
            f"({new_stop:.2f})"
        )

    def _update_ladder(self, candle):
        if not self.position:
            return

        p = self.position

        if p["side"] == "LONG":
            favorable_r = (
                candle["high"] - p["entry"]
            ) / p["one_r_distance"]
        else:
            favorable_r = (
                p["entry"] - candle["low"]
            ) / p["one_r_distance"]

        p["highest_r_reached"] = max(
            p["highest_r_reached"],
            favorable_r,
        )

        if favorable_r >= 5:
            if p["protected_r"] < 4:
                self._move_stop(4)

        elif favorable_r >= 4:
            if p["protected_r"] < 3:
                self._move_stop(3)

        elif favorable_r >= 3:
            if p["protected_r"] < 2:
                self._move_stop(2)

        elif favorable_r >= 2:
            if p["protected_r"] < 1:
                self._move_stop(1)

        elif favorable_r >= 1:
            if p["protected_r"] < 0.5:
                self._move_stop(0.5)

        self._save_state()

    # ==================================================
    # EXCHANGE EXIT SYNC
    # ==================================================

    def _sync_exchange_exit(self):
        if not self.position:
            return False

        p = self.position

        try:
            exchange_position = self.client.get_position(
                self.product_id
            )

            exchange_size = int(
                exchange_position.get("size", 0)
                or 0
            )
        except Exception as error:
            print(
                f"⚠️ Position sync failed: {error}"
            )
            return False

        if exchange_size != 0:
            return False

        # Position is flat. Cancel any sibling protection
        # that may still be resting.
        for order_key in (
            "stop_order_id",
            "tp_order_id",
        ):
            order_id = p.get(order_key)

            if not order_id:
                continue

            try:
                self.client.cancel_order(
                    order_id=order_id,
                    product_id=self.product_id,
                )
            except Exception:
                pass

        print("\n🏁 Exchange reports BTCUSD flat.")
        self.position = None
        self._save_state()

        return True

    # ==================================================
    # STARTUP RECONCILIATION
    # ==================================================

    def reconcile_exchange(self):
        exchange_position = self.client.get_position(
            self.product_id
        )

        exchange_size = int(
            exchange_position.get("size", 0)
            or 0
        )

        if self.position is None and exchange_size != 0:
            self.kill_switch = True
            self._save_state()

            raise RuntimeError(
                "Exchange has an open BTCUSD position "
                "but local state has none. Kill switch "
                "activated; resolve manually."
            )

        if self.position is not None and exchange_size == 0:
            print(
                "♻️ Saved local position is already "
                "flat on Delta. Clearing local state."
            )

            self.position = None
            self._save_state()

    # ==================================================
    # PROCESS CLOSED 15M CANDLE
    # ==================================================

    def process_candle(self, candle, signal=None):
        timestamp = candle["timestamp"]

        if self.last_processed_candle == timestamp:
            return

        self._update_day_from_candle(timestamp)

        self._sync_exchange_exit()

        if self.position:
            self._update_ladder(candle)

        if (
            self.position is None
            and signal is not None
        ):
            self.open_trade(signal)

        self.last_processed_candle = timestamp
        self._save_state()
