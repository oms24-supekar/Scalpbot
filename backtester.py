from datetime import datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


class Backtester:
    def __init__(
        self,
        strategy,
        starting_equity=1000.0,
        margin_per_trade=100.0,
        leverage=200.0,
        risk_fraction_of_margin=0.35,
        fee_rate_per_side=0.0,
        slippage_rate_per_side=0.0,
        session_start_hour=0,
        session_end_hour=24,
        max_entries_per_day=2,
        final_target_r=6.0,
        allowed_entry_hours=None,
    ):
        self.strategy = strategy

        self.starting_equity = starting_equity
        self.equity = starting_equity
        self.peak_equity = starting_equity
        self.max_drawdown_pct = 0.0

        self.margin_per_trade = margin_per_trade
        self.leverage = leverage
        self.risk_fraction = risk_fraction_of_margin

        self.fee_rate = fee_rate_per_side
        self.slippage_rate = slippage_rate_per_side

        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.max_entries_per_day = max_entries_per_day

        # Compatibility only; this model has no fixed TP.
        self.final_target_r = final_target_r

        # If provided, entries are allowed ONLY during these IST hours.
        # Example: {10, 14, 19}
        self.allowed_entry_hours = (
            set(allowed_entry_hours)
            if allowed_entry_hours is not None
            else None
        )

        self.position = None
        self.trades = []

        self.ruined = False
        self.trading_enabled = True

        self.current_ist_date = None
        self.entries_today = 0

    # ==================================================
    # TIME
    # ==================================================

    def _get_ist_datetime(self, timestamp):
        dt = datetime.fromisoformat(timestamp)
        return dt.astimezone(IST)

    def _update_day_counter(self, timestamp):
        ist_date = self._get_ist_datetime(timestamp).date()

        if self.current_ist_date != ist_date:
            self.current_ist_date = ist_date
            self.entries_today = 0

    def _inside_entry_session(self, timestamp):
        ist_dt = self._get_ist_datetime(timestamp)

        # Preferred filtered mode:
        # allow entries only at specific IST hours.
        if self.allowed_entry_hours is not None:
            return ist_dt.hour in self.allowed_entry_hours

        # Fallback to original session window.
        return (
            self.session_start_hour
            <= ist_dt.hour
            < self.session_end_hour
        )

    def _entry_allowed(self, timestamp):
        self._update_day_counter(timestamp)

        if not self.trading_enabled:
            return False

        if not self._inside_entry_session(timestamp):
            return False

        if self.entries_today >= self.max_entries_per_day:
            return False

        if self.equity < self.margin_per_trade:
            self.ruined = True
            self.trading_enabled = False
            return False

        return True

    # ==================================================
    # EXECUTION
    # ==================================================

    def _entry_price(self, signal):
        price = signal["entry"]

        if signal["side"] == "LONG":
            return price * (1 + self.slippage_rate)

        return price * (1 - self.slippage_rate)

    def _exit_price(
        self,
        side,
        raw_price,
    ):
        if side == "LONG":
            return raw_price * (1 - self.slippage_rate)

        return raw_price * (1 + self.slippage_rate)

    # ==================================================
    # POSITION SIZE
    # ==================================================

    def _calculate_position(self, entry_price):
        notional = (
            self.margin_per_trade
            * self.leverage
        )

        btc_quantity = (
            notional
            / entry_price
        )

        risk_dollars = (
            self.margin_per_trade
            * self.risk_fraction
        )

        one_r_distance = (
            risk_dollars
            / btc_quantity
        )

        return (
            notional,
            btc_quantity,
            risk_dollars,
            one_r_distance,
        )

    # ==================================================
    # PRICE AT R
    # ==================================================

    def _price_at_r(
        self,
        side,
        entry,
        one_r,
        multiple,
    ):
        if side == "LONG":
            return entry + one_r * multiple

        return entry - one_r * multiple

    # ==================================================
    # OPEN TRADE
    # ==================================================

    def _open_trade(self, signal):
        if not self._entry_allowed(
            signal["timestamp"]
        ):
            return False

        entry = self._entry_price(signal)

        (
            notional,
            btc_quantity,
            risk_dollars,
            one_r_distance,
        ) = self._calculate_position(entry)

        side = signal["side"]

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

        self.position = {
            "side": side,
            "entry": entry,
            "entry_time": signal["timestamp"],
            "entry_ema": signal["ema"],

            "margin": self.margin_per_trade,
            "leverage": self.leverage,
            "notional": notional,
            "btc_quantity": btc_quantity,

            "risk_dollars": risk_dollars,
            "one_r_distance": one_r_distance,

            "stop_price": stop_price,
            "protected_r": -1.0,
            "highest_r_reached": 0.0,
        }

        self.entries_today += 1

        return True

    # ==================================================
    # CLOSE TRADE
    # ==================================================

    def _close_trade(
        self,
        raw_exit_price,
        exit_time,
        reason,
    ):
        if self.position is None:
            return

        p = self.position

        side = p["side"]
        entry = p["entry"]
        quantity = p["btc_quantity"]

        exit_price = self._exit_price(
            side,
            raw_exit_price,
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

        gross_pnl = (
            pnl_points
            * quantity
        )

        entry_fee = (
            entry
            * quantity
            * self.fee_rate
        )

        exit_fee = (
            exit_price
            * quantity
            * self.fee_rate
        )

        fees = (
            entry_fee
            + exit_fee
        )

        net_pnl = (
            gross_pnl
            - fees
        )

        equity_before = self.equity

        self.equity += net_pnl

        achieved_r = (
            pnl_points
            / p["one_r_distance"]
        )

        trade = {
            "side": side,

            "entry_time": (
                p["entry_time"]
            ),

            "exit_time": exit_time,

            "entry": entry,
            "exit": exit_price,

            "entry_ema": (
                p["entry_ema"]
            ),

            "margin": (
                p["margin"]
            ),

            "initial_risk_dollars": (
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

            "achieved_r": achieved_r,

            "btc_quantity": quantity,

            "leverage": (
                p["leverage"]
            ),

            "notional": (
                p["notional"]
            ),

            "pnl_points": pnl_points,

            "gross_pnl_dollars": (
                gross_pnl
            ),

            "fees": fees,

            "net_pnl_dollars": (
                net_pnl
            ),

            "equity_before": (
                equity_before
            ),

            "equity_after": (
                self.equity
            ),

            "reason": reason,
        }

        self.trades.append(trade)

        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        drawdown = (
            (
                self.peak_equity
                - self.equity
            )
            / self.peak_equity
        ) * 100

        self.max_drawdown_pct = max(
            self.max_drawdown_pct,
            drawdown,
        )

        self.position = None

        if self.equity < self.margin_per_trade:
            self.ruined = True
            self.trading_enabled = False

    # ==================================================
    # STOP
    # ==================================================

    def _stop_hit(self, candle):
        if self.position is None:
            return False

        side = self.position["side"]
        stop = self.position["stop_price"]

        if (
            side == "LONG"
            and candle["low"] <= stop
        ):
            self._close_trade(
                raw_exit_price=stop,
                exit_time=candle["timestamp"],
                reason="TRAILING_STOP",
            )

            return True

        if (
            side == "SHORT"
            and candle["high"] >= stop
        ):
            self._close_trade(
                raw_exit_price=stop,
                exit_time=candle["timestamp"],
                reason="TRAILING_STOP",
            )

            return True

        return False

    # ==================================================
    # TRAIL 1R BELOW HIGHEST WHOLE R
    # ==================================================

    def _update_r_ladder(self, candle):
        """
        No fixed take-profit.

        1R reached  -> stop at 0R
        2R reached  -> stop at +1R
        3R reached  -> stop at +2R
        ...
        10R reached -> stop at +9R

        Stop updates occur on closed candles.
        """
        if self.position is None:
            return False

        p = self.position

        side = p["side"]
        entry = p["entry"]
        one_r = p["one_r_distance"]

        if side == "LONG":
            favorable_r = (
                candle["high"] - entry
            ) / one_r
        else:
            favorable_r = (
                entry - candle["low"]
            ) / one_r

        p["highest_r_reached"] = max(
            p["highest_r_reached"],
            favorable_r,
        )

        highest_r = p["highest_r_reached"]

        if highest_r < 1.0:
            return False

        highest_whole_r = int(highest_r)
        new_protected_r = highest_whole_r - 1

        if new_protected_r <= p["protected_r"]:
            return False

        p["stop_price"] = self._price_at_r(
            side,
            entry,
            one_r,
            new_protected_r,
        )

        p["protected_r"] = float(
            new_protected_r
        )

        return False

    # ==================================================
    # MANAGE OPEN POSITION
    # ==================================================

    def _manage_position(self, candle):
        if self.position is None:
            return

        # IMPORTANT:
        # Position management is ALWAYS active,
        # even outside allowed entry hours.
        stopped = self._stop_hit(candle)

        if stopped:
            return

        self._update_r_ladder(candle)

    # ==================================================
    # SIGNAL
    # ==================================================

    def _process_signal(self, signal):
        if signal is None:
            return

        if self.position is not None:
            return

        self._open_trade(signal)

    # ==================================================
    # PROCESS CANDLE
    # ==================================================

    def process_candle(self, candle):
        self._update_day_counter(
            candle["timestamp"]
        )

        # Existing trade management is 24/7.
        self._manage_position(candle)

        # Strategy still processes every candle,
        # so EMA state remains continuous.
        signal = self.strategy.process_candle(
            candle
        )

        self._process_signal(signal)

    # ==================================================
    # RESULTS
    # ==================================================

    def results(self):
        total = len(self.trades)

        if total == 0:
            return {
                "trades": 0,
                "ruined": self.ruined,
            }

        wins = [
            t
            for t in self.trades
            if t["net_pnl_dollars"] > 0
        ]

        losses = [
            t
            for t in self.trades
            if t["net_pnl_dollars"] < 0
        ]

        breakeven = [
            t
            for t in self.trades
            if abs(
                t["net_pnl_dollars"]
            ) < 0.000001
        ]

        gross_profit = sum(
            t["net_pnl_dollars"]
            for t in wins
        )

        gross_loss = abs(
            sum(
                t["net_pnl_dollars"]
                for t in losses
            )
        )

        if gross_loss > 0:
            profit_factor = (
                gross_profit
                / gross_loss
            )
        else:
            profit_factor = float("inf")

        win_rate = (
            len(wins)
            / total
        ) * 100

        average_trade = (
            sum(
                t["net_pnl_dollars"]
                for t in self.trades
            )
            / total
        )

        total_return = (
            (
                self.equity
                - self.starting_equity
            )
            / self.starting_equity
        ) * 100

        reached_6r = [
            t
            for t in self.trades
            if t["highest_r_reached"] >= 6.0
        ]

        reached_10r = [
            t
            for t in self.trades
            if t["highest_r_reached"] >= 10.0
        ]

        max_r_reached = max(
            (
                t["highest_r_reached"]
                for t in self.trades
            ),
            default=0.0,
        )

        full_losses = [
            t
            for t in self.trades
            if t["achieved_r"] <= -0.9
        ]

        protected_05r = [
            t
            for t in self.trades
            if (
                t["reason"] == "TRAILING_STOP"
                and
                0.4 <= t["achieved_r"] < 0.9
            )
        ]

        protected_1r = [
            t
            for t in self.trades
            if (
                t["reason"] == "TRAILING_STOP"
                and
                0.9 <= t["achieved_r"] < 1.9
            )
        ]

        protected_2r = [
            t
            for t in self.trades
            if (
                t["reason"] == "TRAILING_STOP"
                and
                1.9 <= t["achieved_r"] < 2.9
            )
        ]

        protected_3r = [
            t
            for t in self.trades
            if (
                t["reason"] == "TRAILING_STOP"
                and
                2.9 <= t["achieved_r"] < 3.9
            )
        ]

        protected_4r = [
            t
            for t in self.trades
            if (
                t["reason"] == "TRAILING_STOP"
                and
                3.9 <= t["achieved_r"] < 5.9
            )
        ]

        return {
            "trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),

            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "average_trade_dollars": average_trade,

            "starting_equity": self.starting_equity,
            "ending_equity": self.equity,
            "peak_equity": self.peak_equity,

            "total_return_pct": total_return,
            "max_drawdown_pct": self.max_drawdown_pct,

            "full_losses": len(full_losses),
            "protected_05r": len(protected_05r),
            "protected_1r": len(protected_1r),
            "protected_2r": len(protected_2r),
            "protected_3r": len(protected_3r),
            "protected_4r": len(protected_4r),
            "target_6r": len(reached_6r),
            "reached_6r": len(reached_6r),
            "reached_10r": len(reached_10r),
            "max_r_reached": max_r_reached,

            "ruined": self.ruined,
        }
