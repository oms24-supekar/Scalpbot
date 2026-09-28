import asyncio
import json
import os
from datetime import datetime, timezone

import websockets
from dotenv import load_dotenv


load_dotenv()


def get_websocket_url():
    testnet = (
        os.getenv(
            "DELTA_TESTNET",
            "false",
        ).lower()
        == "true"
    )

    if testnet:
        return (
            "wss://socket-ind-pub."
            "testnet.deltaex.org"
        )

    return (
        "wss://public-socket."
        "india.delta.exchange"
    )


def floor_to_15m(
    timestamp_microseconds,
):
    seconds = (
        timestamp_microseconds
        / 1_000_000
    )

    dt = datetime.fromtimestamp(
        seconds,
        tz=timezone.utc,
    )

    minute = (
        dt.minute
        // 15
        * 15
    )

    return dt.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


async def stream_closed_candles(
    symbol="BTCUSD",
):
    websocket_url = (
        get_websocket_url()
    )

    testnet = (
        os.getenv(
            "DELTA_TESTNET",
            "false",
        ).lower()
        == "true"
    )

    environment = (
        "TESTNET"
        if testnet
        else "PRODUCTION"
    )

    current_bucket = None
    current_candle = None

    while True:
        try:
            async with websockets.connect(
                websocket_url,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:

                subscribe_message = {
                    "type": "subscribe",

                    "payload": {
                        "channels": [
                            {
                                "name": (
                                    "candlestick_15m"
                                ),

                                "symbols": [
                                    symbol
                                ],
                            }
                        ]
                    },
                }

                await ws.send(
                    json.dumps(
                        subscribe_message
                    )
                )

                print(
                    f"\n🟢 Connected to Delta "
                    f"{environment}: "
                    f"{symbol}"
                )

                print(
                    f"WebSocket: "
                    f"{websocket_url}"
                )

                print(
                    "Waiting for completed "
                    "15-minute candles...\n"
                )

                while True:
                    message = (
                        await ws.recv()
                    )

                    data = (
                        json.loads(
                            message
                        )
                    )

                    if (
                        data.get("type")
                        != "candlestick_15m"
                    ):
                        continue

                    publish_timestamp = (
                        data["ts"]
                    )

                    candle_bucket = (
                        floor_to_15m(
                            publish_timestamp
                        )
                    )

                    candle = {
                        "timestamp": (
                            candle_bucket
                            .isoformat()
                        ),

                        "symbol": (
                            data["sy"]
                        ),

                        "open": float(
                            data["o"]
                        ),

                        "high": float(
                            data["h"]
                        ),

                        "low": float(
                            data["l"]
                        ),

                        "close": float(
                            data["c"]
                        ),

                        "volume": float(
                            data.get(
                                "v",
                                0,
                            )
                        ),
                    }

                    # ==================================
                    # FIRST LIVE CANDLE
                    # ==================================

                    if (
                        current_bucket
                        is None
                    ):
                        current_bucket = (
                            candle_bucket
                        )

                        current_candle = (
                            candle
                        )

                        print(
                            "Tracking live 15m "
                            "candle: "
                            f"{current_bucket.isoformat()}"
                        )

                        continue

                    # ==================================
                    # SAME CANDLE
                    # ==================================

                    if (
                        candle_bucket
                        == current_bucket
                    ):
                        current_candle = (
                            candle
                        )

                        continue

                    # ==================================
                    # PREVIOUS CANDLE CLOSED
                    # ==================================

                    closed_candle = (
                        current_candle
                    )

                    print(
                        "\n✅ CLOSED 15M CANDLE"
                    )

                    print(
                        f"Time   : "
                        f"{closed_candle['timestamp']}"
                    )

                    print(
                        f"Open   : "
                        f"{closed_candle['open']}"
                    )

                    print(
                        f"High   : "
                        f"{closed_candle['high']}"
                    )

                    print(
                        f"Low    : "
                        f"{closed_candle['low']}"
                    )

                    print(
                        f"Close  : "
                        f"{closed_candle['close']}"
                    )

                    print(
                        f"Volume : "
                        f"{closed_candle['volume']}"
                    )

                    print(
                        "-" * 60
                    )

                    yield (
                        closed_candle
                    )

                    current_bucket = (
                        candle_bucket
                    )

                    current_candle = (
                        candle
                    )

        except asyncio.CancelledError:
            print(
                "\n🛑 Market stream stopped."
            )

            raise

        except Exception as error:
            print(
                f"\n🔴 WebSocket error: "
                f"{error}"
            )

            print(
                "Reconnecting in "
                "3 seconds..."
            )

            await asyncio.sleep(3)