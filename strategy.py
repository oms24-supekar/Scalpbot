class StrategyEngine:
    def __init__(
        self,
        ema_length=9,
        close_strength_threshold=0.65,
    ):
        self.ema_length = ema_length

        self.alpha = (
            2
            / (ema_length + 1)
        )

        self.close_strength_threshold = (
            close_strength_threshold
        )

        self.closes = []

        self.ema = None
        self.previous_close = None

    # ==================================================
    # STATE
    # ==================================================

    def get_state(self):
        return {
            "ema_length": (
                self.ema_length
            ),

            "close_strength_threshold": (
                self.close_strength_threshold
            ),

            "closes": (
                self.closes[-100:]
            ),

            "ema": (
                self.ema
            ),

            "previous_close": (
                self.previous_close
            ),
        }

    def load_state(self, state):
        if not state:
            return False

        try:
            self.closes = [
                float(value)
                for value
                in state.get(
                    "closes",
                    [],
                )
            ]

            ema = state.get("ema")

            if ema is not None:
                self.ema = float(ema)

            previous_close = state.get(
                "previous_close"
            )

            if previous_close is not None:
                self.previous_close = float(
                    previous_close
                )

            return True

        except Exception:
            return False

    # ==================================================
    # CANDLE STRENGTH
    # ==================================================

    def _bullish_close_strength(
        self,
        candle,
    ):
        candle_range = (
            candle["high"]
            - candle["low"]
        )

        if candle_range <= 0:
            return 0.0

        return (
            candle["close"]
            - candle["low"]
        ) / candle_range

    def _bearish_close_strength(
        self,
        candle,
    ):
        candle_range = (
            candle["high"]
            - candle["low"]
        )

        if candle_range <= 0:
            return 0.0

        return (
            candle["high"]
            - candle["close"]
        ) / candle_range

    # ==================================================
    # STRATEGY
    # ==================================================

    def process_candle(
        self,
        candle,
    ):
        close = float(
            candle["close"]
        )

        self.closes.append(
            close
        )

        if len(self.closes) > 100:
            self.closes = (
                self.closes[-100:]
            )

        # ----------------------------------------------
        # INITIAL EMA
        # ----------------------------------------------

        if self.ema is None:

            if (
                len(self.closes)
                < self.ema_length
            ):
                return None

            self.ema = (
                sum(
                    self.closes[
                        -self.ema_length:
                    ]
                )
                / self.ema_length
            )

            self.previous_close = close

            return None

        previous_ema = self.ema
        previous_close = (
            self.previous_close
        )

        current_ema = (
            close
            * self.alpha
            +
            previous_ema
            * (
                1
                - self.alpha
            )
        )

        bullish_candle = (
            candle["close"]
            > candle["open"]
        )

        bearish_candle = (
            candle["close"]
            < candle["open"]
        )

        bullish_strength = (
            self._bullish_close_strength(
                candle
            )
        )

        bearish_strength = (
            self._bearish_close_strength(
                candle
            )
        )

        ema_rising = (
            current_ema
            > previous_ema
        )

        ema_falling = (
            current_ema
            < previous_ema
        )

        signal = None

        # ==================================================
        # LONG
        # ==================================================

        long_cross = (
            previous_close
            <= previous_ema
            and
            close > current_ema
        )

        long_confirmation = (
            bullish_candle
            and
            bullish_strength
            >= self.close_strength_threshold
            and
            ema_rising
        )

        if (
            long_cross
            and
            long_confirmation
        ):
            signal = {
                "side": "LONG",

                "symbol": (
                    candle["symbol"]
                ),

                "entry": close,

                "timestamp": (
                    candle["timestamp"]
                ),

                "ema": current_ema,

                "previous_ema": (
                    previous_ema
                ),

                "previous_close": (
                    previous_close
                ),

                "close_strength": (
                    bullish_strength
                ),

                "candle_open": (
                    candle["open"]
                ),

                "candle_high": (
                    candle["high"]
                ),

                "candle_low": (
                    candle["low"]
                ),

                "candle_close": (
                    candle["close"]
                ),
            }

        # ==================================================
        # SHORT
        # ==================================================

        short_cross = (
            previous_close
            >= previous_ema
            and
            close < current_ema
        )

        short_confirmation = (
            bearish_candle
            and
            bearish_strength
            >= self.close_strength_threshold
            and
            ema_falling
        )

        if (
            signal is None
            and
            short_cross
            and
            short_confirmation
        ):
            signal = {
                "side": "SHORT",

                "symbol": (
                    candle["symbol"]
                ),

                "entry": close,

                "timestamp": (
                    candle["timestamp"]
                ),

                "ema": current_ema,

                "previous_ema": (
                    previous_ema
                ),

                "previous_close": (
                    previous_close
                ),

                "close_strength": (
                    bearish_strength
                ),

                "candle_open": (
                    candle["open"]
                ),

                "candle_high": (
                    candle["high"]
                ),

                "candle_low": (
                    candle["low"]
                ),

                "candle_close": (
                    candle["close"]
                ),
            }

        self.ema = current_ema
        self.previous_close = close

        return signal