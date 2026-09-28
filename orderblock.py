class OrderBlockDetector:
    def __init__(
        self,
        length=5,
        max_bullish=3,
        max_bearish=3,
        mitigation="Wick"
    ):
        self.length = length
        self.max_bullish = max_bullish
        self.max_bearish = max_bearish
        self.mitigation = mitigation

        self.history = []

        self.bullish_blocks = []
        self.bearish_blocks = []

        # Equivalent to Pine's:
        # var os = 0
        self.os = 0

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _highest(self, key, length):
        recent = self.history[-length:]
        return max(c[key] for c in recent)

    def _lowest(self, key, length):
        recent = self.history[-length:]
        return min(c[key] for c in recent)

    def _volume_pivot_high(self):
        """
        Equivalent idea to:

        ta.pivothigh(volume, length, length)

        Pivot candle is length candles behind the
        currently confirmed candle.
        """

        required = (self.length * 2) + 1

        if len(self.history) < required:
            return False

        window = self.history[-required:]

        pivot_index = self.length

        pivot_volume = window[pivot_index]["volume"]

        other_volumes = [
            candle["volume"]
            for i, candle in enumerate(window)
            if i != pivot_index
        ]

        return pivot_volume > max(other_volumes)

    # --------------------------------------------------
    # Direction state
    # --------------------------------------------------

    def _update_os(self):
        """
        Recreates:

        os :=
            high[length] > upper ? 0 :
            low[length] < lower ? 1 :
            os[1]
        """

        if len(self.history) < self.length + 1:
            return

        pivot_candle = self.history[-(self.length + 1)]

        recent = self.history[-self.length:]

        upper = max(c["high"] for c in recent)
        lower = min(c["low"] for c in recent)

        if pivot_candle["high"] > upper:
            self.os = 0

        elif pivot_candle["low"] < lower:
            self.os = 1

    # --------------------------------------------------
    # Create new OB
    # --------------------------------------------------

    def _create_order_block(self):
        if not self._volume_pivot_high():
            return None

        pivot_candle = self.history[-(self.length + 1)]

        high = pivot_candle["high"]
        low = pivot_candle["low"]

        midpoint = (high + low) / 2

        # -----------------------------
        # Bullish Order Block
        # -----------------------------

        if self.os == 1:

            block = {
                "type": "bullish",
                "top": midpoint,
                "bottom": low,
                "average": (midpoint + low) / 2,
                "created_at": pivot_candle["timestamp"],
                "active": True
            }

            self.bullish_blocks.insert(0, block)

            print("\n🟩 NEW BULLISH ORDER BLOCK")
            print(f"Top    : {block['top']}")
            print(f"Bottom : {block['bottom']}")
            print(f"Time   : {block['created_at']}")

            return block

        # -----------------------------
        # Bearish Order Block
        # -----------------------------

        if self.os == 0:

            block = {
                "type": "bearish",
                "top": high,
                "bottom": midpoint,
                "average": (high + midpoint) / 2,
                "created_at": pivot_candle["timestamp"],
                "active": True
            }

            self.bearish_blocks.insert(0, block)

            print("\n🟥 NEW BEARISH ORDER BLOCK")
            print(f"Top    : {block['top']}")
            print(f"Bottom : {block['bottom']}")
            print(f"Time   : {block['created_at']}")

            return block

        return None

    # --------------------------------------------------
    # Remove mitigated blocks
    # --------------------------------------------------

    def _remove_mitigated(self):
        if len(self.history) < self.length:
            return

        recent = self.history[-self.length:]

        if self.mitigation == "Close":

            target_bull = min(
                c["close"] for c in recent
            )

            target_bear = max(
                c["close"] for c in recent
            )

        else:

            # LuxAlgo default = Wick
            target_bull = min(
                c["low"] for c in recent
            )

            target_bear = max(
                c["high"] for c in recent
            )

        # -----------------------------
        # Bullish mitigation
        # -----------------------------

        remaining_bullish = []

        for block in self.bullish_blocks:

            if target_bull < block["bottom"]:

                print("\n❌ BULLISH OB MITIGATED")
                print(f"Bottom : {block['bottom']}")

            else:
                remaining_bullish.append(block)

        self.bullish_blocks = remaining_bullish

        # -----------------------------
        # Bearish mitigation
        # -----------------------------

        remaining_bearish = []

        for block in self.bearish_blocks:

            if target_bear > block["top"]:

                print("\n❌ BEARISH OB MITIGATED")
                print(f"Top : {block['top']}")

            else:
                remaining_bearish.append(block)

        self.bearish_blocks = remaining_bearish

    # --------------------------------------------------
    # Main candle processor
    # --------------------------------------------------

    def process_candle(self, candle):
        """
        Run this ONCE for every CLOSED 15m candle.
        """

        self.history.append(candle)

        # Keep memory reasonable
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

        if len(self.history) < self.length + 1:
            return

        self._update_os()

        if len(self.history) >= (self.length * 2) + 1:
            self._create_order_block()

        self._remove_mitigated()

    # --------------------------------------------------
    # Blocks actually visible like TradingView
    # --------------------------------------------------

    def get_visible_bullish(self):
        return self.bullish_blocks[
            :self.max_bullish
        ]

    def get_visible_bearish(self):
        return self.bearish_blocks[
            :self.max_bearish
        ]

    # --------------------------------------------------
    # Debug output
    # --------------------------------------------------

    def print_active_blocks(self):
        print("\n==============================")
        print("ACTIVE ORDER BLOCKS")
        print("==============================")

        print("\n🟩 BULLISH")

        bullish = self.get_visible_bullish()

        if not bullish:
            print("None")

        for i, block in enumerate(bullish, 1):
            print(
                f"{i}. "
                f"{block['bottom']} → "
                f"{block['top']}"
            )

        print("\n🟥 BEARISH")

        bearish = self.get_visible_bearish()

        if not bearish:
            print("None")

        for i, block in enumerate(bearish, 1):
            print(
                f"{i}. "
                f"{block['bottom']} → "
                f"{block['top']}"
            )

        print("==============================\n")