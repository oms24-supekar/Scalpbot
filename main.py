import asyncio
from datetime import datetime

from history_loader import (
    fetch_historical_candles
)

from market import (
    stream_closed_candles
)

from strategy import (
    StrategyEngine
)

from paper_executor import (
    PaperExecutor
)


def to_dt(timestamp):
    return datetime.fromisoformat(
        timestamp
    )


async def main():
    print(
        "\n🤖 BTC EMA9 LOCAL PAPER BOT"
    )

    print(
        "=" * 60
    )

    strategy = StrategyEngine(
        ema_length=9,
        close_strength_threshold=0.65,
    )

    executor = PaperExecutor(
        starting_equity=1000.0,
        margin_per_trade=100.0,
        leverage=200.0,
        risk_fraction=0.35,
        session_start_hour=10,
        session_end_hour=24,
        max_entries_per_day=6,
        final_target_r=6.0,
    )

    # ==================================================
    # RECOVERY HISTORY
    # ==================================================

    print(
        "\n📥 Loading recovery history..."
    )

    history = fetch_historical_candles(
        symbol="BTCUSD",
        resolution="15m",
        limit_candles=2000,
    )

    if len(history) < 20:
        raise RuntimeError(
            "Not enough historical candles."
        )

    last_saved = (
        executor.last_processed_candle
    )

    # ==================================================
    # FIRST START
    # ==================================================

    if last_saved is None:
        print(
            "\n🆕 First start."
        )

        print(
            "Warming EMA..."
        )

        for candle in history:
            strategy.process_candle(
                candle
            )

        executor.last_processed_candle = (
            history[-1]["timestamp"]
        )

        executor._save_state()

        print(
            f"✅ EMA warmed using "
            f"{len(history)} candles"
        )

    # ==================================================
    # RESTART / RECOVERY
    # ==================================================

    else:
        print(
            "\n♻️ RECOVERY MODE"
        )

        print(
            f"Last processed:"
            f"\n{last_saved}"
        )

        last_dt = to_dt(
            last_saved
        )

        warmup = []
        missed = []

        for candle in history:
            candle_dt = to_dt(
                candle["timestamp"]
            )

            if candle_dt <= last_dt:
                warmup.append(
                    candle
                )
            else:
                missed.append(
                    candle
                )

        # ----------------------------------------------
        # Rebuild EMA state
        # ----------------------------------------------

        if warmup:
            for candle in warmup:
                strategy.process_candle(
                    candle
                )

        else:
            # Saved candle older than available history.
            # Warm from first 100 available candles.
            for candle in history[:100]:
                strategy.process_candle(
                    candle
                )

        # ----------------------------------------------
        # Replay missed candles
        # ----------------------------------------------

        if missed:
            print(
                f"\n⏪ Missed candles: "
                f"{len(missed)}"
            )

            for candle in missed:
                signal = (
                    strategy.process_candle(
                        candle
                    )
                )

                executor.process_candle(
                    candle,
                    signal,
                )

                print(
                    f"↻ "
                    f"{candle['timestamp']}"
                )

            print(
                "✅ Recovery complete."
            )

        else:
            print(
                "✅ No missed candles."
            )

    # ==================================================
    # SETTINGS
    # ==================================================

    print(
        "\n⚙️ ACTIVE SETTINGS"
    )

    print(
        "BTCUSD / 15m"
    )

    print(
        "EMA9 confirmed crossover"
    )

    print(
        "10:00 → 24:00 IST"
    )

    print(
        "Max 6 entries/day"
    )

    print(
        "$100 margin"
    )

    print(
        "200x leverage"
    )

    print(
        "$35 initial risk"
    )

    print(
        "\nWaiting for live market...\n"
    )

    # ==================================================
    # LIVE
    # ==================================================

    async for candle in stream_closed_candles(
        symbol="BTCUSD"
    ):
        # Skip candle already processed
        if (
            executor.last_processed_candle
            is not None
        ):
            if (
                to_dt(
                    candle["timestamp"]
                )
                <= to_dt(
                    executor.last_processed_candle
                )
            ):
                continue

        print(
            "\n"
            + "-" * 60
        )

        print(
            "🕯️ LIVE CLOSED 15M"
        )

        print(
            f"Time  : "
            f"{candle['timestamp']}"
        )

        print(
            f"Open  : "
            f"{candle['open']}"
        )

        print(
            f"High  : "
            f"{candle['high']}"
        )

        print(
            f"Low   : "
            f"{candle['low']}"
        )

        print(
            f"Close : "
            f"{candle['close']}"
        )

        # ----------------------------------------------
        # SIGNAL
        # ----------------------------------------------

        signal = (
            strategy.process_candle(
                candle
            )
        )

        if signal:
            print(
                "\n⚡ EMA9 SIGNAL"
            )

            print(
                f"Side  : "
                f"{signal['side']}"
            )

            print(
                f"Entry : "
                f"{signal['entry']:.2f}"
            )

            print(
                f"EMA9  : "
                f"{signal['ema']:.2f}"
            )

        # ----------------------------------------------
        # EXECUTE PAPER LOGIC
        # ----------------------------------------------

        executor.process_candle(
            candle,
            signal,
        )

        # ----------------------------------------------
        # STATUS
        # ----------------------------------------------

        if executor.position:
            p = executor.position

            print(
                "\n📍 OPEN POSITION"
            )

            print(
                f"Side       : "
                f"{p['side']}"
            )

            print(
                f"Entry      : "
                f"{p['entry']:.2f}"
            )

            print(
                f"Current SL : "
                f"{p['stop_price']:.2f}"
            )

            print(
                f"Protected  : "
                f"{p['protected_r']:+.1f}R"
            )

            print(
                f"Best move  : "
                f"{p['highest_r_reached']:.2f}R"
            )

        print(
            f"\n💰 Equity : "
            f"${executor.equity:.2f}"
        )

        print(
            f"📊 Entries: "
            f"{executor.entries_today}/6"
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )