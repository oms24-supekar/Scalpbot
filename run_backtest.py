import csv
import os

from history_loader import (
    fetch_historical_range
)

from strategy import StrategyEngine
from backtester import Backtester


# ==================================================
# CORE SETTINGS
# ==================================================

STARTING_EQUITY = 1000.0

MARGIN_PER_TRADE = 100.0

LEVERAGE = 200.0

RISK_FRACTION = 0.35

FEE_PER_SIDE = 0.0

SLIPPAGE_PER_SIDE = 0.0

MAX_ENTRIES_PER_DAY = 6

FINAL_TARGET_R = 6.0


# ==================================================
# HISTORICAL PERIODS
# ==================================================

PERIODS = [
    {
        "name": "MAR_AUG_2025",
        "start": "2025-03-01",
        "end": "2025-08-31",
    },

    {
        "name": "SEP_2025_MAR_2026",
        "start": "2025-09-01",
        "end": "2026-03-12",
    },

    {
        "name": "MAR_SEP_2026",
        "start": "2026-03-13",
        "end": "2026-09-27",
    },
]


# ==================================================
# ENTRY-HOUR VARIANTS
# ==================================================

VARIANTS = [
    {
        "name": "FINAL_10_14",
        "hours": {
            10,
            14,
        },
    },
]


# ==================================================
# SAVE INDIVIDUAL TRADE CSV
# ==================================================

def save_trades(
    trades,
    period_name,
    variant_name,
):
    if not trades:
        return

    os.makedirs(
        "backtests",
        exist_ok=True,
    )

    file_path = (
        "backtests/"
        f"{period_name}_"
        f"{variant_name}.csv"
    )

    with open(
        file_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=trades[0].keys(),
        )

        writer.writeheader()
        writer.writerows(
            trades
        )

    print(
        f"💾 Saved: "
        f"{file_path}"
    )


# ==================================================
# RUN SINGLE BACKTEST
# ==================================================

def run_single_test(
    candles,
    period_name,
    variant_name,
    allowed_hours,
):

    strategy = StrategyEngine(
        ema_length=9,
        close_strength_threshold=0.65,
    )

    backtester = Backtester(
        strategy=strategy,

        starting_equity=(
            STARTING_EQUITY
        ),

        margin_per_trade=(
            MARGIN_PER_TRADE
        ),

        leverage=(
            LEVERAGE
        ),

        risk_fraction_of_margin=(
            RISK_FRACTION
        ),

        fee_rate_per_side=(
            FEE_PER_SIDE
        ),

        slippage_rate_per_side=(
            SLIPPAGE_PER_SIDE
        ),

        session_start_hour=0,

        session_end_hour=24,

        max_entries_per_day=(
            MAX_ENTRIES_PER_DAY
        ),

        final_target_r=(
            FINAL_TARGET_R
        ),

        allowed_entry_hours=(
            allowed_hours
        ),
    )

    for candle in candles:
        backtester.process_candle(
            candle
        )

    results = (
        backtester.results()
    )

    save_trades(
        backtester.trades,
        period_name,
        variant_name,
    )

    if results["trades"] == 0:
        return {
            "period": period_name,
            "variant": variant_name,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "average_trade": 0.0,
            "net_pnl": 0.0,
            "return_pct": 0.0,
            "max_drawdown": 0.0,
            "ending_equity": (
                STARTING_EQUITY
            ),
            "target_6r": 0,
        }

    net_pnl = (
        results["ending_equity"]
        - results["starting_equity"]
    )

    return {
        "period": (
            period_name
        ),

        "variant": (
            variant_name
        ),

        "trades": (
            results["trades"]
        ),

        "wins": (
            results["wins"]
        ),

        "losses": (
            results["losses"]
        ),

        "win_rate": (
            results["win_rate"]
        ),

        "profit_factor": (
            results["profit_factor"]
        ),

        "average_trade": (
            results[
                "average_trade_dollars"
            ]
        ),

        "net_pnl": (
            net_pnl
        ),

        "return_pct": (
            results[
                "total_return_pct"
            ]
        ),

        "max_drawdown": (
            results[
                "max_drawdown_pct"
            ]
        ),

        "ending_equity": (
            results[
                "ending_equity"
            ]
        ),

        "target_6r": (
            results[
                "target_6r"
            ]
        ),
    }


# ==================================================
# PRINT PERIOD RESULTS
# ==================================================

def print_single_result(
    result
):
    print(
        "\n"
        + "-" * 75
    )

    print(
        f"Period  : "
        f"{result['period']}"
    )

    print(
        f"Variant : "
        f"{result['variant']}"
    )

    print(
        f"Trades  : "
        f"{result['trades']}"
    )

    print(
        f"WR      : "
        f"{result['win_rate']:.2f}%"
    )

    print(
        f"PF      : "
        f"{result['profit_factor']:.2f}"
    )

    print(
        f"Net PnL : "
        f"${result['net_pnl']:.2f}"
    )

    print(
        f"Return  : "
        f"{result['return_pct']:.2f}%"
    )

    print(
        f"Max DD  : "
        f"{result['max_drawdown']:.2f}%"
    )

    print(
        f"6R hits : "
        f"{result['target_6r']}"
    )


# ==================================================
# SAVE MASTER COMPARISON
# ==================================================

def save_comparison(
    results
):
    os.makedirs(
        "backtests",
        exist_ok=True,
    )

    file_path = (
        "backtests/"
        "ema9_final_10_14_multi_period.csv"
    )

    with open(
        file_path,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=results[0].keys(),
        )

        writer.writeheader()
        writer.writerows(
            results
        )

    print(
        f"\n💾 Final 10+14 comparison saved:"
        f"\n{file_path}"
    )


# ==================================================
# SUMMARY BY VARIANT
# ==================================================

def summarize_variants(
    all_results
):
    print(
        "\n"
        + "=" * 105
    )

    print(
        "📊 MULTI-PERIOD VARIANT SUMMARY"
    )

    print(
        "=" * 105
    )

    print(
        f"{'Variant':<14}"
        f"{'Periods':>9}"
        f"{'Trades':>10}"
        f"{'Avg WR':>10}"
        f"{'Avg PF':>10}"
        f"{'Net PnL':>12}"
        f"{'Worst DD':>12}"
        f"{'Profitable':>12}"
    )

    print(
        "-" * 105
    )

    for variant in VARIANTS:

        variant_name = (
            variant["name"]
        )

        rows = [
            result
            for result in all_results
            if (
                result["variant"]
                == variant_name
            )
        ]

        total_trades = sum(
            row["trades"]
            for row in rows
        )

        average_wr = (
            sum(
                row["win_rate"]
                for row in rows
            )
            / len(rows)
        )

        average_pf = (
            sum(
                row["profit_factor"]
                for row in rows
            )
            / len(rows)
        )

        total_pnl = sum(
            row["net_pnl"]
            for row in rows
        )

        worst_dd = max(
            row["max_drawdown"]
            for row in rows
        )

        profitable_periods = sum(
            1
            for row in rows
            if row["net_pnl"] > 0
        )

        print(
            f"{variant_name:<14}"
            f"{len(rows):>9}"
            f"{total_trades:>10}"
            f"{average_wr:>9.2f}%"
            f"{average_pf:>10.2f}"
            f"${total_pnl:>11.2f}"
            f"{worst_dd:>11.2f}%"
            f"{profitable_periods:>9}/"
            f"{len(rows)}"
        )

    print(
        "=" * 105
    )


# ==================================================
# MAIN
# ==================================================

def main():

    print(
        "\n🔥 EMA9 MULTI-PERIOD "
        "HOUR FILTER TEST"
    )

    print(
        "=" * 70
    )

    print(
        "\nFrozen strategy:"
    )

    print(
        "EMA9"
    )

    print(
        "Close strength = 0.65"
    )

    print(
        "1R = $35"
    )

    print(
        "Leverage = 200x"
    )

    print(
        "R ladder = "
        "0.5R / 1R / 2R / "
        "3R / 4R / 6R"
    )

    print(
        "\nVariants:"
    )

    for variant in VARIANTS:

        print(
            f"{variant['name']} "
            f"→ "
            f"{sorted(variant['hours'])}"
        )

    print(
        "\nPeriods:"
    )

    for period in PERIODS:

        print(
            f"{period['name']} "
            f"→ "
            f"{period['start']} "
            f"to "
            f"{period['end']}"
        )

    all_results = []

    # ==================================================
    # LOOP PERIODS
    # ==================================================

    for period in PERIODS:

        print(
            "\n"
            + "=" * 70
        )

        print(
            f"📅 LOADING "
            f"{period['name']}"
        )

        print(
            "=" * 70
        )

        candles = (
            fetch_historical_range(
                symbol="BTCUSD",

                resolution="15m",

                start_date=(
                    period["start"]
                ),

                end_date=(
                    period["end"]
                ),
            )
        )

        print(
            f"\n✅ Loaded "
            f"{len(candles)} candles"
        )

        if len(candles) < 20:

            print(
                "⚠️ Not enough candles. "
                "Skipping period."
            )

            continue

        # ==============================================
        # LOOP VARIANTS
        # ==============================================

        for variant in VARIANTS:

            print(
                "\n🧪 Testing "
                f"{variant['name']}..."
            )

            result = (
                run_single_test(
                    candles=candles,

                    period_name=(
                        period["name"]
                    ),

                    variant_name=(
                        variant["name"]
                    ),

                    allowed_hours=(
                        variant["hours"]
                    ),
                )
            )

            all_results.append(
                result
            )

            print_single_result(
                result
            )

    # ==================================================
    # MASTER TABLE
    # ==================================================

    print(
        "\n\n"
        + "=" * 125
    )

    print(
        "📊 COMPLETE COMPARISON"
    )

    print(
        "=" * 125
    )

    print(
        f"{'Period':<24}"
        f"{'Variant':<14}"
        f"{'Trades':>8}"
        f"{'WR':>9}"
        f"{'PF':>9}"
        f"{'Avg $':>10}"
        f"{'Net PnL':>12}"
        f"{'Return':>10}"
        f"{'Max DD':>10}"
        f"{'6R':>7}"
    )

    print(
        "-" * 125
    )

    for result in all_results:

        print(
            f"{result['period']:<24}"
            f"{result['variant']:<14}"
            f"{result['trades']:>8}"
            f"{result['win_rate']:>8.2f}%"
            f"{result['profit_factor']:>9.2f}"
            f"${result['average_trade']:>9.2f}"
            f"${result['net_pnl']:>11.2f}"
            f"{result['return_pct']:>9.2f}%"
            f"{result['max_drawdown']:>9.2f}%"
            f"{result['target_6r']:>7}"
        )

    print(
        "=" * 125
    )

    summarize_variants(
        all_results
    )

    if all_results:
        save_comparison(
            all_results
        )


if __name__ == "__main__":
    main()