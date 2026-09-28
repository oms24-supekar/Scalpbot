import time
import requests
from datetime import datetime, timezone


PRODUCTION_REST = "https://api.india.delta.exchange"

MAX_PER_REQUEST = 2000


RESOLUTION_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}


def _parse_candles(
    raw_candles,
    symbol,
):
    candles = {}

    for item in raw_candles:
        ts = int(
            item["time"]
        )

        dt = datetime.fromtimestamp(
            ts,
            tz=timezone.utc,
        )

        candles[ts] = {
            "timestamp": (
                dt.isoformat()
            ),

            "symbol": symbol,

            "open": float(
                item["open"]
            ),

            "high": float(
                item["high"]
            ),

            "low": float(
                item["low"]
            ),

            "close": float(
                item["close"]
            ),

            "volume": float(
                item.get(
                    "volume",
                    0,
                )
            ),
        }

    return candles


# ==================================================
# LATEST N CANDLES
# ==================================================

def fetch_historical_candles(
    symbol="BTCUSD",
    resolution="15m",
    limit_candles=50000,
):
    if resolution not in RESOLUTION_SECONDS:
        raise ValueError(
            f"Unsupported resolution: "
            f"{resolution}"
        )

    candle_seconds = (
        RESOLUTION_SECONDS[
            resolution
        ]
    )

    all_candles = {}

    end_timestamp = int(
        datetime.now(
            timezone.utc
        ).timestamp()
    )

    remaining = (
        limit_candles
    )

    batch = 1

    print(
        f"\n📦 Target candles: "
        f"{limit_candles}"
    )

    while remaining > 0:
        batch_size = min(
            MAX_PER_REQUEST,
            remaining,
        )

        start_timestamp = (
            end_timestamp
            - (
                batch_size
                * candle_seconds
            )
        )

        print(
            f"📥 Batch {batch} "
            f"| requesting "
            f"~{batch_size} candles..."
        )

        response = requests.get(
            (
                PRODUCTION_REST
                + "/v2/history/candles"
            ),
            params={
                "resolution": resolution,
                "symbol": symbol,
                "start": start_timestamp,
                "end": end_timestamp,
            },
            timeout=30,
        )

        response.raise_for_status()

        payload = (
            response.json()
        )

        if not payload.get(
            "success"
        ):
            raise RuntimeError(
                payload
            )

        raw = payload.get(
            "result",
            []
        )

        if not raw:
            break

        parsed = (
            _parse_candles(
                raw,
                symbol,
            )
        )

        all_candles.update(
            parsed
        )

        oldest = min(
            parsed.keys()
        )

        print(
            f"✅ Received: "
            f"{len(raw)} "
            f"| Total unique: "
            f"{len(all_candles)}"
        )

        end_timestamp = (
            oldest
            - candle_seconds
        )

        remaining = (
            limit_candles
            - len(all_candles)
        )

        batch += 1

        time.sleep(
            0.25
        )

    candles = [
        all_candles[key]
        for key
        in sorted(
            all_candles
        )
    ]

    if (
        len(candles)
        > limit_candles
    ):
        candles = (
            candles[
                -limit_candles:
            ]
        )

    _print_summary(
        candles
    )

    return candles


# ==================================================
# FIXED DATE RANGE
# ==================================================

def fetch_historical_range(
    symbol="BTCUSD",
    resolution="15m",
    start_date="2025-09-01",
    end_date="2026-03-12",
):
    if resolution not in RESOLUTION_SECONDS:
        raise ValueError(
            f"Unsupported resolution: "
            f"{resolution}"
        )

    candle_seconds = (
        RESOLUTION_SECONDS[
            resolution
        ]
    )

    start_dt = datetime.strptime(
        start_date,
        "%Y-%m-%d",
    ).replace(
        tzinfo=timezone.utc,
    )

    end_dt = datetime.strptime(
        end_date,
        "%Y-%m-%d",
    ).replace(
        hour=23,
        minute=59,
        second=59,
        tzinfo=timezone.utc,
    )

    start_timestamp = int(
        start_dt.timestamp()
    )

    end_timestamp = int(
        end_dt.timestamp()
    )

    all_candles = {}

    current_start = (
        start_timestamp
    )

    batch = 1

    print(
        f"\n📅 Historical range:"
        f"\n{start_date} "
        f"→ {end_date}"
    )

    while (
        current_start
        <= end_timestamp
    ):
        current_end = min(
            current_start
            + (
                MAX_PER_REQUEST
                * candle_seconds
            ),
            end_timestamp,
        )

        print(
            f"📥 Batch {batch}"
        )

        response = requests.get(
            (
                PRODUCTION_REST
                + "/v2/history/candles"
            ),
            params={
                "resolution": resolution,
                "symbol": symbol,
                "start": current_start,
                "end": current_end,
            },
            timeout=30,
        )

        response.raise_for_status()

        payload = (
            response.json()
        )

        if not payload.get(
            "success"
        ):
            raise RuntimeError(
                payload
            )

        raw = payload.get(
            "result",
            []
        )

        if raw:
            parsed = (
                _parse_candles(
                    raw,
                    symbol,
                )
            )

            all_candles.update(
                parsed
            )

        print(
            f"✅ Received: "
            f"{len(raw)} "
            f"| Total unique: "
            f"{len(all_candles)}"
        )

        current_start = (
            current_end
            + candle_seconds
        )

        batch += 1

        time.sleep(
            0.25
        )

    candles = [
        all_candles[key]
        for key
        in sorted(
            all_candles
        )
    ]

    _print_summary(
        candles
    )

    return candles


# ==================================================
# SUMMARY
# ==================================================

def _print_summary(
    candles
):
    print(
        f"\n🔥 FINAL HISTORY: "
        f"{len(candles)} candles"
    )

    if candles:
        print(
            f"Oldest: "
            f"{candles[0]['timestamp']}"
        )

        print(
            f"Newest: "
            f"{candles[-1]['timestamp']}"
        )