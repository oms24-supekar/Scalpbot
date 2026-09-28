import time

from delta_client import DeltaClient


SYMBOL = "BTCUSD"
SIZE = 1


def position_size(client, product_id):
    position = client.get_position(product_id)

    return int(
        position.get("size", 0)
        or 0
    )


def safe_cancel(
    client,
    order,
    product_id,
    label,
):
    if not order:
        return

    order_id = order.get("id")

    if not order_id:
        return

    try:
        client.cancel_order(
            order_id=order_id,
            product_id=product_id,
        )

        print(
            f"✅ Cancelled {label}"
        )

    except Exception as error:
        print(
            f"⚠️ Could not cancel {label}: "
            f"{error}"
        )


def flatten_position(
    client,
    product_id,
):
    size = position_size(
        client,
        product_id,
    )

    if size == 0:
        print(
            "✅ Position already flat."
        )
        return

    if size > 0:
        side = "sell"
    else:
        side = "buy"

    close_size = abs(size)

    client.place_market_order(
        product_id=product_id,
        size=close_size,
        side=side,
        client_order_id=(
            f"protect-flat-"
            f"{int(time.time())}"
        ),
        reduce_only=True,
    )

    time.sleep(2)

    final_size = position_size(
        client,
        product_id,
    )

    print(
        f"Final position size: "
        f"{final_size}"
    )


def main():
    print(
        "\n⚠️ PROTECTIVE ORDER LIVE TEST"
    )

    print(
        "=" * 60
    )

    client = DeltaClient()

    if not client.allow_orders:
        raise RuntimeError(
            "DELTA_ALLOW_ORDERS must be true."
        )

    product = client.get_product(
        SYMBOL
    )

    product_id = int(
        product["id"]
    )

    tick_size = float(
        product["tick_size"]
    )

    print(
        f"Product ID : "
        f"{product_id}"
    )

    print(
        f"Tick size  : "
        f"{tick_size}"
    )

    # ==========================================
    # MUST START FLAT
    # ==========================================

    existing_size = position_size(
        client,
        product_id,
    )

    if existing_size != 0:
        raise RuntimeError(
            "BTCUSD position is not flat. "
            "Test aborted."
        )

    print(
        "\nThis will:"
    )

    print(
        "1. BUY 1 BTCUSD contract"
    )

    print(
        "2. Place a reduce-only stop-market"
    )

    print(
        "3. Place a reduce-only TP-market"
    )

    print(
        "4. Verify both conditional orders"
    )

    print(
        "5. Edit the stop trigger"
    )

    print(
        "6. Cancel both protection orders"
    )

    print(
        "7. Close the 1-contract position"
    )

    confirmation = input(
        "\nType EXACTLY: "
        "TEST PROTECTION\n> "
    )

    if confirmation != "TEST PROTECTION":
        print(
            "❌ Cancelled."
        )
        return

    stop_order = None
    tp_order = None

    try:
        # ======================================
        # OPEN
        # ======================================

        open_id = (
            f"protect-open-"
            f"{int(time.time())}"
        )

        print(
            "\n🚀 Opening 1 contract..."
        )

        open_order = (
            client.place_market_order(
                product_id=product_id,
                size=SIZE,
                side="buy",
                client_order_id=open_id,
                reduce_only=False,
            )
        )

        print(
            open_order
        )

        time.sleep(2)

        position = client.get_position(
            product_id
        )

        size = int(
            position.get("size", 0)
            or 0
        )

        if size != 1:
            raise RuntimeError(
                f"Expected size 1, "
                f"got {size}."
            )

        entry = float(
            position["entry_price"]
        )

        print(
            f"\n✅ LONG opened @ "
            f"{entry}"
        )

        # ======================================
        # CHOOSE DISTANT TEST TRIGGERS
        # ======================================

        raw_stop = (
            entry * 0.98
        )

        raw_tp = (
            entry * 1.02
        )

        stop_price = float(
            client.round_to_tick(
                raw_stop,
                tick_size,
            )
        )

        tp_price = float(
            client.round_to_tick(
                raw_tp,
                tick_size,
            )
        )

        print(
            f"Test stop : "
            f"{stop_price}"
        )

        print(
            f"Test TP   : "
            f"{tp_price}"
        )

        unique = str(
            int(time.time())
        )

        # ======================================
        # STOP LOSS
        # ======================================

        print(
            "\n🛡️ Placing stop-market..."
        )

        stop_order = (
            client.place_stop_market(
                product_id=product_id,
                size=SIZE,
                side="sell",
                stop_price=stop_price,
                client_order_id=(
                    f"protect-sl-{unique}"
                ),
            )
        )

        print(
            stop_order
        )

        # ======================================
        # TAKE PROFIT
        # ======================================

        print(
            "\n🎯 Placing TP-market..."
        )

        tp_order = (
            client.place_take_profit_market(
                product_id=product_id,
                size=SIZE,
                side="sell",
                stop_price=tp_price,
                client_order_id=(
                    f"protect-tp-{unique}"
                ),
            )
        )

        print(
            tp_order
        )

        time.sleep(1)

        # ======================================
        # VERIFY
        # ======================================

        stop_check = (
            client.get_order_by_client_id(
                f"protect-sl-{unique}"
            )
        )

        tp_check = (
            client.get_order_by_client_id(
                f"protect-tp-{unique}"
            )
        )

        print(
            "\n✅ STOP STATUS"
        )

        print(
            "State:",
            stop_check.get("state")
        )

        print(
            "Stop price:",
            stop_check.get("stop_price")
        )

        print(
            "Reduce only:",
            stop_check.get("reduce_only")
        )

        print(
            "\n✅ TP STATUS"
        )

        print(
            "State:",
            tp_check.get("state")
        )

        print(
            "Stop price:",
            tp_check.get("stop_price")
        )

        print(
            "Reduce only:",
            tp_check.get("reduce_only")
        )

        # ======================================
        # EDIT STOP
        # ======================================

        edited_stop = float(
            client.round_to_tick(
                entry * 0.985,
                tick_size,
            )
        )

        print(
            f"\n✏️ Editing stop to: "
            f"{edited_stop}"
        )

        edited = (
            client.edit_stop_order(
                order_id=(
                    stop_order["id"]
                ),
                product_id=product_id,
                new_stop_price=(
                    edited_stop
                ),
            )
        )

        print(
            edited
        )

        print(
            "\n✅ Protective-order "
            "test passed."
        )

    finally:
        print(
            "\n🧹 CLEANUP"
        )

        safe_cancel(
            client,
            stop_order,
            product_id,
            "stop order",
        )

        safe_cancel(
            client,
            tp_order,
            product_id,
            "TP order",
        )

        try:
            flatten_position(
                client,
                product_id,
            )

        except Exception as error:
            print(
                "\n🚨 AUTOMATIC FLATTEN "
                "FAILED:"
            )

            print(
                error
            )

            print(
                "CHECK DELTA MANUALLY NOW."
            )


if __name__ == "__main__":
    main()