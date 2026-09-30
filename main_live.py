import asyncio
import os

from dotenv import load_dotenv

from delta_client import DeltaClient
from delta_executor import DeltaExecutor
from history_loader import fetch_historical_candles
from market import stream_closed_candles
from strategy import StrategyEngine
from telegram_control import TelegramControl


load_dotenv()


async def main():
    print("\n🚀 BTC EMA9 LIVE BOT")
    print("=" * 60)

    live_auto = (
        os.getenv(
            "LIVE_AUTO_TRADING",
            "false",
        ).lower()
        == "true"
    )

    confirm_trades = (
        os.getenv(
            "TELEGRAM_CONFIRM_TRADES",
            "true",
        ).lower()
        == "true"
    )

    telegram = TelegramControl()
    telegram.start()

    client = DeltaClient()

    strategy = StrategyEngine(
        ema_length=9,
        close_strength_threshold=0.65,
    )

    executor = DeltaExecutor(
        client=client,
        symbol="BTCUSD",

        # Start tiny. Edit later only after validating logs.
        contracts_per_trade=24,
        risk_dollars=3.5,

        # LONG  -> signal close + $12.50 limit cap
        # SHORT -> signal close - $12.50 limit cap
        entry_limit_offset=12.5,

        session_start_hour=0,
        session_end_hour=24,
        allowed_entry_hours={10, 14},

        max_entries_per_day=2,
        # Compatibility only; no fixed TP in live exit logic.
        final_target_r=6.0,

        # Hard safety cap.
        max_contracts=24,
        max_daily_loss_usd=7.0,

        live_auto_trading=live_auto,

        notifier=telegram.notify,

        trade_confirmation_callback=(
            telegram.request_trade_confirmation
            if confirm_trades
            else None
        ),
    )

    executor.reconcile_exchange()

    telegram.set_handlers(
        status_provider=executor.telegram_status,
        kill_callback=executor.activate_kill_switch,
        resume_callback=executor.deactivate_kill_switch,
    )

    telegram.notify(
        "🟢 ScalpBot AWS started\n"
        "Environment: INDIA PRODUCTION\n"
        "Entry hours: 10:00 & 14:00 IST\n"
        "Exit: unlimited trail 1R behind peak\n"
        f"Orders: "
        f"{'ENABLED' if client.allow_orders else 'DISABLED'}\n"
        f"Live auto: "
        f"{'ON' if live_auto else 'OFF'}\n"
        f"Telegram confirmation: "
        f"{'ON' if confirm_trades else 'OFF'}"
    )

    print("\n📥 Warming EMA from production history...")

    history = fetch_historical_candles(
        symbol="BTCUSD",
        resolution="15m",
        limit_candles=2000,
    )

    if len(history) < 20:
        raise RuntimeError(
            "Not enough historical candles."
        )

    # Rebuild EMA through all available completed history.
    # IMPORTANT: old signals are NOT executed on restart.
    for candle in history:
        strategy.process_candle(candle)

    newest_history_timestamp = (
        history[-1]["timestamp"]
    )

    executor.last_processed_candle = (
        newest_history_timestamp
    )
    executor._save_state()

    print(
        f"✅ EMA warmed with "
        f"{len(history)} candles"
    )

    print(
        f"Newest history candle: "
        f"{newest_history_timestamp}"
    )

    print("\n⚙️ LIVE CONFIG")
    print("Environment       : INDIA PRODUCTION")
    print("BTCUSD            : 15m")
    print("Entry             : IOC LIMIT")
    print("Entry hours (IST) : 10:00-10:59 & 14:00-14:59")
    print("LONG cap          : signal + $12.50")
    print("SHORT cap         : signal - $12.50")
    print("Initial SL        : STOP-MARKET")
    print("Take profit       : NONE")
    print("Exit logic        : trail 1R below highest whole R")
    print("Contracts/trade   : 24")
    print("Risk/trade        : $3.50")
    print("Daily loss cap    : $7.00")
    print("Max entries/day   : 2")
    print(
        f"LIVE AUTO         : "
        f"{'ON' if live_auto else 'OFF'}"
    )

    print(
        f"Telegram confirm  : "
        f"{'ON' if confirm_trades else 'OFF'}"
    )

    if not live_auto:
        print(
            "\n🛡️ Signals will be detected, but "
            "live entry will be blocked until "
            "LIVE_AUTO_TRADING=true."
        )

    print("\nWaiting for production candles...\n")

    async for candle in stream_closed_candles(
        symbol="BTCUSD"
    ):
        if (
            executor.last_processed_candle
            is not None
            and candle["timestamp"]
            <= executor.last_processed_candle
        ):
            continue

        print("\n" + "-" * 60)
        print("🕯️ CLOSED 15M")
        print(f"Time  : {candle['timestamp']}")
        print(f"Open  : {candle['open']}")
        print(f"High  : {candle['high']}")
        print(f"Low   : {candle['low']}")
        print(f"Close : {candle['close']}")

        signal = strategy.process_candle(
            candle
        )

        if signal:
            print("\n⚡ EMA9 SIGNAL")
            print(f"Side  : {signal['side']}")
            print(f"Entry : {signal['entry']:.2f}")
            print(f"EMA9  : {signal['ema']:.2f}")

        executor.process_candle(
            candle,
            signal,
        )

        if executor.position:
            p = executor.position

            print("\n📍 LIVE POSITION")
            print(f"Side       : {p['side']}")
            print(f"Entry      : {p['entry']:.2f}")
            print(f"Stop       : {p['stop_price']:.2f}")
            print("Exit       : trail 1R below peak")
            print(
                f"Protected  : "
                f"{p['protected_r']:+.1f}R"
            )
            print(
                f"Best move  : "
                f"{p['highest_r_reached']:.2f}R"
            )


if __name__ == "__main__":
    asyncio.run(main())
