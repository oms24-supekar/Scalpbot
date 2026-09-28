import asyncio
from datetime import datetime

from delta_client import DeltaClient
from delta_executor import DeltaExecutor
from history_loader import fetch_historical_candles
from market import stream_closed_candles
from strategy import StrategyEngine


def to_dt(timestamp):
    return datetime.fromisoformat(timestamp)


async def main():
    print("\n🤖 DELTA PRODUCTION DRY-RUN BOT")
    print("=" * 60)

    # ==========================================
    # DELTA CLIENT
    # ==========================================

    client = DeltaClient()

    # ==========================================
    # STRATEGY
    # ==========================================

    strategy = StrategyEngine(
        ema_length=9,
        close_strength_threshold=0.65,
    )

    # ==========================================
    # SAFE EXECUTOR
    # ==========================================

    executor = DeltaExecutor(
        client=client,
        symbol="BTCUSD",

        margin_per_trade=5.0,
        leverage=20,
        risk_fraction=0.20,

        session_start_hour=10,
        session_end_hour=24,
        max_entries_per_day=6,

        final_target_r=6.0,

        dry_run=True,

        max_margin_per_trade=5.0,
        max_risk_dollars=1.0,
        max_contracts=10,
    )

    # ==========================================
    # HISTORY / RECOVERY
    # ==========================================

    print("\n📥 Loading EMA recovery history...")

    history = fetch_historical_candles(
        symbol="BTCUSD",
        resolution="15m",
        limit_candles=2000,
    )

    if len(history) < 20:
        raise RuntimeError(
            "Not enough historical candles."
        )

    last_saved = executor.last_processed_candle

    # ==========================================
    # FIRST START
    # ==========================================

    if last_saved is None:
        print("\n🆕 FIRST START")
        print("Warming EMA...")

        for candle in history:
            strategy.process_candle(candle)

        executor.last_processed_candle = (
            history[-1]["timestamp"]
        )

        executor._save_state()

        print(
            f"✅ EMA warmed with "
            f"{len(history)} candles"
        )

        print(
            f"Last historical candle: "
            f"{executor.last_processed_candle}"
        )

    # ==========================================
    # RESTART / MISSED-CANDLE RECOVERY
    # ==========================================

    else:
        print("\n♻️ RECOVERY MODE")

        print(
            f"Last processed candle: "
            f"{last_saved}"
        )

        saved_dt = to_dt(last_saved)

        old_candles = []
        missed_candles = []

        for candle in history:
            candle_dt = to_dt(
                candle["timestamp"]
            )

            if candle_dt <= saved_dt:
                old_candles.append(candle)
            else:
                missed_candles.append(candle)

        for candle in old_candles:
            strategy.process_candle(candle)

        if missed_candles:
            print(
                f"⏪ Missed candles: "
                f"{len(missed_candles)}"
            )

            for candle in missed_candles:
                signal = strategy.process_candle(
                    candle
                )

                executor.process_candle(
                    candle,
                    signal,
                )

                print(
                    f"↻ {candle['timestamp']}"
                )

            print(
                "✅ Recovery complete."
            )

        else:
            print(
                "✅ No missed candles."
            )

    # ==========================================
    # SETTINGS
    # ==========================================

    print("\n⚙️ ACTIVE SETTINGS")

    print("Environment   : INDIA PRODUCTION")
    print("Execution     : DRY RUN")
    print("BTCUSD / 15m")
    print("EMA9 confirmed crossover")
    print("Entry window  : 10:00 → 24:00 IST")
    print("Max entries   : 6/day")
    print("Margin        : $5")
    print("Leverage      : 20x")
    print("1R risk       : $1")
    print("Real orders   : BLOCKED")

    print(
        "\nWaiting for live candles...\n"
    )

    # ==========================================
    # LIVE STREAM
    # ==========================================

    async for candle in stream_closed_candles(
        symbol="BTCUSD"
    ):
        # Skip already-processed candles
        if (
            executor.last_processed_candle
            is not None
        ):
            if (
                to_dt(candle["timestamp"])
                <=
                to_dt(
                    executor.last_processed_candle
                )
            ):
                continue

        print(
            "\n"
            + "-" * 60
        )

        print(
            "🕯️ CLOSED 15M"
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

        # ==========================================
        # STRATEGY SIGNAL
        # ==========================================

        signal = strategy.process_candle(
            candle
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

        # ==========================================
        # DRY-RUN EXECUTION
        # ==========================================

        executor.process_candle(
            candle,
            signal,
        )

        print(
            f"\n📊 Entries today: "
            f"{executor.entries_today}/"
            f"{executor.max_entries_per_day}"
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )