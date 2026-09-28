import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class PaperExecutor:
    def __init__(
        self,
        starting_equity=1000.0,
        margin_per_trade=100.0,
        leverage=200.0,
        risk_fraction=0.35,
        session_start_hour=10,
        session_end_hour=24,
        max_entries_per_day=6,
        final_target_r=6.0,
    ):
        self.starting_equity = starting_equity
        self.equity = starting_equity
        self.peak_equity = starting_equity

        self.margin_per_trade = margin_per_trade
        self.leverage = leverage
        self.risk_fraction = risk_fraction

        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.max_entries_per_day = max_entries_per_day

        self.final_target_r = final_target_r

        self.position = None

        self.current_ist_date = None
        self.entries_today = 0

        self.trade_number = 0

        # Last completed 15m candle that the bot
        # fully processed.
        self.last_processed_candle = None

        self.state_dir = "state"
        self.trade_dir = "paper_trades"

        self.state_file = os.path.join(
            self.state_dir,
            "paper_state.json",
        )

        self.trade_file = os.path.join(
            self.trade_dir,
            "btc_ema9_live_paper.csv",
        )

        os.makedirs(
            self.state_dir,
            exist_ok=True,
        )

        os.makedirs(
            self.trade_dir,
            exist_ok=True,
        )

        self._load_state()

    # ==================================================
    # STATE
    # ==================================================

    def _state_payload(self):
        return {
            "version": 2,

            "starting_equity": (
                self.starting_equity
            ),

            "equity": (
                self.equity
            ),

            "peak_equity": (
                self.peak_equity
            ),

            "trade_number": (
                self.trade_number
            ),

            "entries_today": (
                self.entries_today
            ),

            "current_ist_date": (
                str(self.current_ist_date)
                if self.current_ist_date
                else None
            ),

            "last_processed_candle": (
                self.last_processed_candle
            ),

            "position": (
                self.position
            ),
        }

    def _save_state(self):
        temp_file = (
            self.state_file
            + ".tmp"
        )

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self._state_payload(),
                file,
                indent=2,
            )

        os.replace(
            temp_file,
            self.state_file,
        )

    def _load_state(self):
        if not os.path.exists(
            self.state_file
        ):
            print(
                "🆕 No saved paper state found."
            )

            self._save_state()
            return

        try:
            with open(
                self.state_file,
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

            self.equity = float(
                data.get(
                    "equity",
                    self.starting_equity,
                )
            )

            self.peak_equity = float(
                data.get(
                    "peak_equity",
                    self.equity,
                )
            )

            self.trade_number = int(
                data.get(
                    "trade_number",
                    0,
                )
            )

            self.entries_today = int(
                data.get(
                    "entries_today",
                    0,
                )
            )

            self.last_processed_candle = (
                data.get(
                    "last_processed_candle"
                )
            )

            saved_date = data.get(
                "current_ist_date"
            )

            if saved_date:
                self.current_ist_date = (
                    datetime.strptime(
                        saved_date,
                        "%Y-%m-%d",
                    ).date()
                )

            self.position = data.get(
                "position"
            )

            today = datetime.now(
                IST
            ).date()

            if (
                self.current_ist_date
                != today
            ):
                self.current_ist_date = today
                self.entries_today = 0

            print(
                "\n♻️ PAPER STATE RESTORED"
            )

            print(
                f"Equity        : "
                f"${self.equity:.2f}"
            )

            print(
                f"Trade number  : "
                f"{self.trade_number}"
            )

            print(
                f"Entries today : "
                f"{self.entries_today}/"
                f"{self.max_entries_per_day}"
            )

            print(
                f"Last candle   : "
                f"{self.last_processed_candle}"
            )

            if self.position:
                print(
                    "\n📍 OPEN POSITION RESTORED"
                )

                print(
                    f"Side       : "
                    f"{self.position['side']}"
                )

                print(
                    f"Entry      : "
                    f"{self.position['entry']:.2f}"
                )

                print(
                    f"Current SL : "
                    f"{self.position['stop_price']:.2f}"
                )

                print(
                    f"Protected  : "
                    f"{self.position['protected_r']:+.1f}R"
                )

            self._save_state()

        except Exception as error:
            print(
                f"\n❌ State load error: "
                f"{error}"
            )

            self.position = None
            self.equity = (
                self.starting_equity
            )
            self.peak_equity = (
                self.starting_equity
            )

            self.trade_number = 0
            self.entries_today = 0
            self.last_processed_candle = None

            self.current_ist_date = (
                datetime.now(IST).date()
            )

            self._save_state()

    # ==================================================
    # TIME
    # ==================================================

    def _get_ist_datetime(
        self,
        timestamp,
    ):
        return datetime.fromisoformat(
            timestamp
        ).astimezone(
            IST
        )

    def _update_day(
        self,
        timestamp,
    ):
        ist_date = (
            self._get_ist_datetime(
                timestamp
            ).date()
        )

        if (
            self.current_ist_date
            != ist_date
        ):
            self.current_ist_date = (
                ist_date
            )

            self.entries_today = 0

            print(
                f"\n🌅 NEW IST DAY: "
                f"{ist_date}"
            )

            self._save_state()

    def _inside_session(
        self,
        timestamp,
    ):
        hour = (
            self._get_ist_datetime(
                timestamp
            ).hour
        )

        return (
            self.session_start_hour
            <= hour
            < self.session_end_hour
        )

    def _entry_allowed(
        self,
        timestamp,
    ):
        self._update_day(
            timestamp
        )

        if not self._inside_session(
            timestamp
        ):
            return False

        if (
            self.entries_today
            >= self.max_entries_per_day
        ):
            return False

        if (
            self.equity
            < self.margin_per_trade
        ):
            return False

        return True

    # ==================================================
    # POSITION SIZE
    # ==================================================

    def _calculate_position(
        self,
        entry_price,
    ):
        notional = (
            self.margin_per_trade
            * self.leverage
        )

        quantity = (
            notional
            / entry_price
        )

        risk_dollars = (
            self.margin_per_trade
            * self.risk_fraction
        )

        one_r_distance = (
            risk_dollars
            / quantity
        )

        return (
            notional,
            quantity,
            risk_dollars,
            one_r_distance,
        )

    def _price_at_r(
        self,
        side,
        entry,
        one_r,
        multiple,
    ):
        if side == "LONG":
            return (
                entry
                + one_r * multiple
            )

        return (
            entry
            - one_r * multiple
        )

    # ==================================================
    # OPEN
    # ==================================================

    def open_trade(
        self,
        signal,
    ):
        if self.position is not None:
            return False

        if not self._entry_allowed(
            signal["timestamp"]
        ):
            return False

        entry = float(
            signal["entry"]
        )

        side = signal["side"]

        (
            notional,
            quantity,
            risk_dollars,
            one_r_distance,
        ) = self._calculate_position(
            entry
        )

        if side == "LONG":
            stop_price = (
                entry
                - one_r_distance
            )
        else:
            stop_price = (
                entry
                + one_r_distance
            )

        self.trade_number += 1
        self.entries_today += 1

        self.position = {
            "trade_id": (
                self.trade_number
            ),

            "side": side,

            "entry": entry,

            "entry_time": (
                signal["timestamp"]
            ),

            "entry_ema": float(
                signal["ema"]
            ),

            "margin": (
                self.margin_per_trade
            ),

            "leverage": (
                self.leverage
            ),

            "notional": (
                notional
            ),

            "btc_quantity": (
                quantity
            ),

            "risk_dollars": (
                risk_dollars
            ),

            "one_r_distance": (
                one_r_distance
            ),

            "stop_price": (
                stop_price
            ),

            "protected_r": -1.0,

            "highest_r_reached": 0.0,
        }

        self._save_state()

        print(
            "\n"
            + "=" * 60
        )

        print(
            "🚀 PAPER TRADE OPENED"
        )

        print(
            f"Side        : {side}"
        )

        print(
            f"Entry       : {entry:.2f}"
        )

        print(
            f"Initial SL  : {stop_price:.2f}"
        )

        print(
            f"1R distance : {one_r_distance:.2f}"
        )

        print(
            f"Risk        : ${risk_dollars:.2f}"
        )

        print(
            f"Entries     : "
            f"{self.entries_today}/"
            f"{self.max_entries_per_day}"
        )

        print(
            "=" * 60
        )

        return True

    # ==================================================
    # CSV
    # ==================================================

    def _save_trade(
        self,
        trade,
    ):
        exists = os.path.exists(
            self.trade_file
        )

        with open(
            self.trade_file,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=trade.keys(),
            )

            if not exists:
                writer.writeheader()

            writer.writerow(
                trade
            )

    # ==================================================
    # CLOSE
    # ==================================================

    def close_trade(
        self,
        exit_price,
        exit_time,
        reason,
    ):
        if self.position is None:
            return

        p = self.position

        entry = p["entry"]
        side = p["side"]
        quantity = p["btc_quantity"]

        exit_price = float(
            exit_price
        )

        if side == "LONG":
            pnl_points = (
                exit_price
                - entry
            )
        else:
            pnl_points = (
                entry
                - exit_price
            )

        pnl_dollars = (
            pnl_points
            * quantity
        )

        achieved_r = (
            pnl_points
            / p["one_r_distance"]
        )

        equity_before = (
            self.equity
        )

        self.equity += (
            pnl_dollars
        )

        self.peak_equity = max(
            self.peak_equity,
            self.equity,
        )

        trade = {
            "trade_id": p["trade_id"],
            "side": side,

            "entry_time": (
                p["entry_time"]
            ),

            "exit_time": (
                exit_time
            ),

            "entry": entry,
            "exit": exit_price,

            "entry_ema": (
                p["entry_ema"]
            ),

            "margin": (
                p["margin"]
            ),

            "leverage": (
                p["leverage"]
            ),

            "quantity": (
                quantity
            ),

            "risk_dollars": (
                p["risk_dollars"]
            ),

            "one_r_distance": (
                p["one_r_distance"]
            ),

            "highest_r_reached": (
                p["highest_r_reached"]
            ),

            "protected_r": (
                p["protected_r"]
            ),

            "achieved_r": (
                achieved_r
            ),

            "pnl_dollars": (
                pnl_dollars
            ),

            "equity_before": (
                equity_before
            ),

            "equity_after": (
                self.equity
            ),

            "reason": (
                reason
            ),
        }

        self._save_trade(
            trade
        )

        self.position = None

        self._save_state()

        print(
            "\n"
            + "=" * 60
        )

        print(
            "🏁 PAPER TRADE CLOSED"
        )

        print(
            f"Side   : {side}"
        )

        print(
            f"Result : {achieved_r:+.2f}R"
        )

        print(
            f"PnL    : ${pnl_dollars:+.2f}"
        )

        print(
            f"Equity : ${self.equity:.2f}"
        )

        print(
            f"Reason : {reason}"
        )

        print(
            "=" * 60
        )

    # ==================================================
    # STOP
    # ==================================================

    def _check_stop(
        self,
        candle,
    ):
        if self.position is None:
            return False

        p = self.position
        stop = p["stop_price"]

        if (
            p["side"] == "LONG"
            and candle["low"] <= stop
        ):
            self.close_trade(
                stop,
                candle["timestamp"],
                "TRAILING_STOP",
            )

            return True

        if (
            p["side"] == "SHORT"
            and candle["high"] >= stop
        ):
            self.close_trade(
                stop,
                candle["timestamp"],
                "TRAILING_STOP",
            )

            return True

        return False

    # ==================================================
    # LADDER
    # ==================================================

    def _update_ladder(
        self,
        candle,
    ):
        if self.position is None:
            return

        p = self.position

        side = p["side"]
        entry = p["entry"]
        one_r = p["one_r_distance"]

        if side == "LONG":
            favorable_r = (
                candle["high"]
                - entry
            ) / one_r
        else:
            favorable_r = (
                entry
                - candle["low"]
            ) / one_r

        old_highest = (
            p["highest_r_reached"]
        )

        p["highest_r_reached"] = max(
            old_highest,
            favorable_r,
        )

        if favorable_r >= 6:
            target = self._price_at_r(
                side,
                entry,
                one_r,
                6,
            )

            self.close_trade(
                target,
                candle["timestamp"],
                "TARGET_6R",
            )

            return

        levels = [
            (5, 4),
            (4, 3),
            (3, 2),
            (2, 1),
            (1, 0.5),
        ]

        for reached, protected in levels:
            if favorable_r >= reached:
                if (
                    p["protected_r"]
                    < protected
                ):
                    p["stop_price"] = (
                        self._price_at_r(
                            side,
                            entry,
                            one_r,
                            protected,
                        )
                    )

                    p["protected_r"] = (
                        protected
                    )

                    print(
                        f"🔒 {reached}R reached "
                        f"→ protecting +"
                        f"{protected}R"
                    )

                break

        self._save_state()

    # ==================================================
    # PROCESS CANDLE
    # ==================================================

    def process_candle(
        self,
        candle,
        signal=None,
    ):
        timestamp = (
            candle["timestamp"]
        )

        # Duplicate protection
        if (
            self.last_processed_candle
            == timestamp
        ):
            return False

        self._update_day(
            timestamp
        )

        stopped = self._check_stop(
            candle
        )

        if not stopped:
            self._update_ladder(
                candle
            )

        if (
            self.position is None
            and signal is not None
        ):
            self.open_trade(
                signal
            )

        self.last_processed_candle = (
            timestamp
        )

        self._save_state()

        return True